# Telegram Configuration Guide for Meshgram

## Overview
This guide explains how to properly configure Telegram integration for Meshgram, ensuring messages from Meshtastic arrive correctly in Telegram groups.

## Configuration Parameters

### telegram_bot_token
- **Required**: Yes
- **Format**: Bot token from @BotFather (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
- **How to get**: Create a bot with @BotFather on Telegram and copy the token

### telegram_chat_id
- **Required**: Yes
- **Format**: Integer (negative for groups/channels, positive for private chats)
- **Group IDs**: Negative values (e.g., `-4911418011`)
- **Channel IDs**: Negative values starting with `-100` (e.g., `-1001234567890`)
- **Private chat IDs**: Positive values (e.g., `4911418011`)

### telegram_default_channel
- **Required**: No (defaults to 0)
- **Format**: Non-negative integer (0, 1, 2, etc.)
- **Purpose**: Filters which Meshtastic channel messages get broadcast to Telegram
- **Note**: This is a Meshtastic channel number, NOT a Telegram chat ID

### telegram_authorized_users
- **Required**: No (if empty, all users are authorized)
- **Format**: Comma-separated list of user IDs (e.g., `123456789,987654321`)

## Getting Chat IDs

### For Groups
1. Add your bot to the Telegram group
2. Make the bot an administrator (recommended for full functionality)
3. Send a message to the group
4. Use one of these methods to get the chat ID:

#### Method 1: Bot API
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```
Look for `"chat":{"id":<CHAT_ID>`

#### Method 2: Python Script
```python
import requests

def get_chat_id(bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    response = requests.get(url)
    data = response.json()
    if data['ok'] and data['result']:
        for update in data['result']:
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                print(f"Chat ID: {chat_id}")
                break

get_chat_id("YOUR_BOT_TOKEN")
```

### For Channels
1. Add your bot as an administrator to the channel
2. Use the same methods as above
3. Channel IDs always start with `-100`

## Common Issues and Solutions

### Issue: "Chat not found" error
**Cause**: Incorrect chat_id or bot not added to chat
**Solution**:
- Verify the chat_id is correct
- Ensure bot is added to the group/channel
- For channels, ensure bot has posting permissions

### Issue: "Not enough rights" error
**Cause**: Bot lacks permissions in the chat
**Solution**:
- Make the bot an administrator in the group/channel
- Ensure bot has "Post Messages" permission for channels

### Issue: Messages not sending to group
**Cause**: chat_id is positive (private chat) instead of negative (group)
**Solution**:
- Change `telegram_chat_id` to negative value for groups
- Verify bot is in the group and has permissions

### Issue: Wrong channel messages appearing
**Cause**: telegram_default_channel not set correctly
**Solution**:
- Set `telegram_default_channel` to match your desired Meshtastic channel
- Use 0 for default channel, higher numbers for other channels

## Configuration Validation

The system now includes enhanced validation:

- **Chat ID format checking**: Warns about private vs group/channel IDs
- **Bot permissions verification**: Tests actual access during setup
- **Configuration backups**: Automatic backups before changes
- **Detailed error messages**: Clear guidance on fixing issues

## Best Practices

1. **Always use negative chat_ids for groups/channels**
2. **Make your bot an administrator** for full functionality
3. **Test configuration** after changes
4. **Keep backups** of working configurations
5. **Monitor logs** for validation warnings

## Example Configuration

```ini
[telegram]
telegram_bot_token = 7937645315:AAFcF0868nWIgK5zbjrlMMdIUNTJtOM2n7c
telegram_chat_id = -4911418011
telegram_authorized_users = 493352084
telegram_default_channel = -4911418011
meshtastic_default_node_id = !4a300a5c
meshtastic_local_nodes = !4a300a5c,!da5acde0
```

## Troubleshooting Commands

### Test Configuration
```bash
python -c "from modules.meshgram_integration.config_manager import ConfigManager; cm = ConfigManager(); cm.validate_config(); print('Configuration valid')"
```

### List Backups
```bash
python -c "from modules.meshgram_integration.config_manager import ConfigManager; cm = ConfigManager(); print('\n'.join(cm.list_backups()))"
```

### Rollback Configuration
```bash
python -c "from modules.meshgram_integration.config_manager import ConfigManager; cm = ConfigManager(); cm.rollback_config('path/to/backup.ini')"
```

## Support

If you encounter issues:
1. Check the logs for detailed error messages
2. Verify all configuration parameters
3. Test bot permissions in Telegram
4. Use the validation tools above
5. Check that chat_ids are negative for groups/channels