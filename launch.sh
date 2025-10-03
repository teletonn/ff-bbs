#!/bin/bash
# This script launches the meshing-around bot, web dashboard, or other tools in a Python virtual environment.

cd "$(dirname "$0")"

if [ ! -f "config.ini" ]; then
    cp config.template config.ini
fi

# activate the virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found, this tool just launches the .py in venv"
    exit 1
fi

# --- MODIFIED LAUNCH LOGIC ---

# Store process IDs of background tasks
PIDS=()

# Flags to check what to do
run_legacy_command=false
start_mesh=false
start_webui=false

# Handle legacy commands if they are the only argument
if [ "$#" -eq 1 ]; then
    if [[ "$1" == pong* ]]; then
        echo "Starting Pong Bot..."
        python3 pong_bot.py
        run_legacy_command=true
    elif [ "$1" == "html" ]; then
        python3 etc/report_generator.py
        run_legacy_command=true
    elif [ "$1" == "html5" ]; then
        python3 etc/report_generator5.py
        run_legacy_command=true
    elif [[ "$1" == add* ]]; then
        python3 script/addFav.py
        run_legacy_command=true
    fi
fi

# If a legacy command was run, we can exit
if [ "$run_legacy_command" = true ]; then
    deactivate
    exit 0
fi

# Parse all arguments for modern concurrent execution
for arg in "$@"; do
    case $arg in
        mesh)
            start_mesh=true
            ;;
        webui)
            start_webui=true
            ;;
    esac
done

# Start mesh bot if requested
if [ "$start_mesh" = true ]; then
    echo "Starting Mesh Bot in the background..."
    python3 mesh_bot.py &
    PIDS+=($!)
fi

# Start web UI if requested
if [ "$start_webui" = true ]; then
    echo "Starting Web UI on port 8000 in the background..."
    echo "Note: Running on port 8000, no superuser privileges required."
    uvicorn webui.main:app --host 0.0.0.0 --port 8000 &
    PIDS+=($!)
fi

# If we started any background processes, wait for them
if [ ${#PIDS[@]} -gt 0 ]; then
    echo "Services are running. Press Ctrl+C to stop all services."
    # Trap Ctrl+C to kill all child processes of this script
    trap "trap - SIGINT SIGTERM; echo -e '\nStopping all services...'; kill 0; exit" SIGINT SIGTERM
    wait
else
    # If no valid arguments were provided and no legacy command was run
    if [ "$run_legacy_command" = false ]; then
        echo "Usage: $0 [mesh] [webui]"
        echo "  mesh      - Start the mesh bot."
        echo "  webui     - Start the web dashboard."
        echo
        echo "Legacy commands (use only one):"
        echo "  $0 <pong|html|html5|addfav>"
        exit 1
    fi
fi

deactivate