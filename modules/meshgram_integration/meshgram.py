import asyncio
from typing import Optional, List, Union
from meshtastic.serial_interface import SerialInterface
from meshtastic.tcp_interface import TCPInterface
from modules.meshgram_integration.meshtastic_interface import MeshtasticInterface
from modules.meshgram_integration.telegram_interface import TelegramInterface
from modules.meshgram_integration.message_processor import MessageProcessor
from modules.meshgram_integration.config_manager import ConfigManager
from modules import log

class MeshgramIntegration:
    """Integration class for Meshgram Telegram bot functionality within the main project."""

    def __init__(self, meshtastic_interface_instance: Union[SerialInterface, TCPInterface], config: Optional[ConfigManager] = None) -> None:
        self.logger = log.logger
        self.meshtastic_interface = meshtastic_interface_instance
        self.config = config or ConfigManager()
        self.meshtastic: Optional[MeshtasticInterface] = None
        self.telegram: Optional[TelegramInterface] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.tasks: list = []
        self.is_shutting_down: bool = False
        self.is_initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the Meshgram integration with the provided Meshtastic interface."""
        if self.is_initialized:
            self.logger.warning("Meshgram integration already initialized")
            return

        self.logger.info("Initializing Meshgram integration...")

        try:
            # Validate configuration
            self.config.validate_config()

            # Setup Meshtastic interface with the provided external interface
            self.meshtastic = MeshtasticInterface(self.config, self.meshtastic_interface)
            await self.meshtastic.setup()

            # Setup Telegram interface
            self.telegram = TelegramInterface(self.config)
            await self.telegram.setup()

            # Setup message processor
            self.message_processor = MessageProcessor(self.meshtastic, self.telegram, self.config)

            self.is_initialized = True
            self.logger.info("Meshgram integration initialized successfully")

        except Exception as e:
            self.logger.error(f"Error during Meshgram integration initialization: {e}", exc_info=True)
            await self.shutdown()
            raise

    async def start(self) -> None:
        """Start the Meshgram integration tasks."""
        if not self.is_initialized:
            await self.initialize()

        self.logger.info("Starting Meshgram integration...")

        # Start background tasks
        self.tasks = [
            asyncio.create_task(self.message_processor.process_messages()),
            asyncio.create_task(self.meshtastic.process_thread_safe_queue()),
            asyncio.create_task(self.meshtastic.process_pending_messages()),
            asyncio.create_task(self.telegram.start_polling()),
        ]

        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            self.logger.info("Meshgram integration received cancellation signal.")
        except Exception as e:
            self.logger.error(f"Unexpected error in Meshgram integration: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown the Meshgram integration."""
        if self.is_shutting_down:
            self.logger.info("Meshgram integration shutdown already in progress, skipping.")
            return

        self.is_shutting_down = True
        self.logger.info("Shutting down Meshgram integration...")

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        # Shutdown components in reverse order of creation
        components = [self.message_processor, self.telegram, self.meshtastic]
        for component in components:
            if component:
                try:
                    await component.close()
                except Exception as e:
                    self.logger.error(f"Error closing {component.__class__.__name__}: {e}", exc_info=True)

        self.is_initialized = False
        self.is_shutting_down = False
        self.logger.info("Meshgram integration shutdown complete.")

    def is_enabled(self) -> bool:
        """Check if the integration is enabled based on configuration."""
        try:
            self.config.get('telegram.telegram_bot_token')
            return True
        except KeyError:
            return False

# Factory function to create and start the integration
async def create_meshgram_integration(meshtastic_interface: Union[SerialInterface, TCPInterface], config: Optional[ConfigManager] = None) -> MeshgramIntegration:
    """Create a MeshgramIntegration instance with the provided Meshtastic interface."""
    integration = MeshgramIntegration(meshtastic_interface, config)
    await integration.initialize()
    return integration