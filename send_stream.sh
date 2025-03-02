#!/bin/bash

# Default values
RTMP_URL="rtmp://localhost:1935/live/stream"
SAMPLE_VIDEO="sample_videos/high_fps_sample.mp4"
# Jellyfish video at 120fps
SAMPLE_VIDEO_URL="https://media.xiph.org/video/derf/jellyfish-120-mbps-hd.mkv"
# Alternative: Tears of Steel clip (has good motion)
ALT_VIDEO_URL="https://download.blender.org/demo/movies/ToS/tears_of_steel_1080p.mov"

# Function to print usage instructions
print_usage() {
    echo "Usage: $0 [-i input_file] [-u rtmp_url]"
    echo "  -i : Input video file (optional)"
    echo "  -u : RTMP URL (default: $RTMP_URL)"
    echo "Example: $0 -i video.mp4 -u rtmp://server:1935/live/stream"
}

# Function to verify video file using ffprobe
verify_video() {
    local input_file=$1
    echo -e "\nVerifying video file: $input_file"
    
    # Check if file exists
    if [ ! -f "$input_file" ]; then
        echo "Error: File not found: $input_file"
        return 1
    fi
    
    # Get video properties using ffprobe
    local video_info
    if ! video_info=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height,duration,r_frame_rate,bit_rate \
        -of json "$input_file" 2>&1); then
        echo "Error: Failed to get video properties"
        return 1
    fi
    
    # Extract and display video properties
    echo "Video properties:"
    echo "Width: $(echo "$video_info" | grep -o '"width":[^,]*' | cut -d':' -f2) px"
    echo "Height: $(echo "$video_info" | grep -o '"height":[^,]*' | cut -d':' -f2) px"
    echo "Duration: $(echo "$video_info" | grep -o '"duration":[^,]*' | cut -d':' -f2) seconds"
    echo "Frame rate: $(echo "$video_info" | grep -o '"r_frame_rate":"[^"]*"' | cut -d'"' -f4)"
    
    # Get bitrate if available
    local bitrate=$(echo "$video_info" | grep -o '"bit_rate":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$bitrate" ]; then
        echo "Bitrate: $(echo "scale=2; $bitrate/1000000" | bc) Mbps"
    fi
    
    # Extract frame rate as a number for comparison
    local fps_num=$(echo "$video_info" | grep -o '"r_frame_rate":"[^"]*"' | cut -d'"' -f4 | awk -F'/' '{print $1/$2}')
    
    # Check if frame rate is high enough
    if (( $(echo "$fps_num < 60" | bc -l) )); then
        echo "Warning: Source video frame rate ($fps_num FPS) is less than 60 FPS."
        echo "The stream will be converted to 60 FPS, but may not look as smooth as a native high FPS source."
    else
        echo "Source video has high frame rate ($fps_num FPS), suitable for 60+ FPS streaming."
    fi
    
    return 0
}

# Function to download sample video
download_sample() {
    local output_path=$1
    local url=$2
    
    # Create directory if it doesn't exist
    mkdir -p "$(dirname "$output_path")"
    
    echo "Downloading high frame rate sample video..."
    echo "This may take a few minutes depending on your internet connection."
    
    if command -v wget &> /dev/null; then
        wget -O "$output_path" "$url" --progress=bar:force
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "$output_path" "$url"
    else
        echo "Error: Neither wget nor curl is installed"
        return 1
    fi
    
    if [ $? -eq 0 ]; then
        echo "Sample video downloaded successfully"
        return 0
    else
        echo "Error downloading sample video. Trying alternative source..."
        if command -v wget &> /dev/null; then
            wget -O "$output_path" "$ALT_VIDEO_URL" --progress=bar:force
        elif command -v curl &> /dev/null; then
            curl -L --progress-bar -o "$output_path" "$ALT_VIDEO_URL"
        fi
        
        if [ $? -eq 0 ]; then
            echo "Alternative sample video downloaded successfully"
            return 0
        else
            echo "Error downloading alternative sample video"
            return 1
        fi
    fi
}

# Function to stream video to RTMP server
stream_to_rtmp() {
    local input_file=$1
    local rtmp_url=$2
    
    # Verify video file first
    if ! verify_video "$input_file"; then
        return 1
    fi
    
    echo -e "\nStarting high-quality 60 FPS stream to $rtmp_url"
    echo "Press Ctrl+C to stop streaming"
    
    # Get source frame rate
    local source_fps=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 \
        "$input_file" | awk -F'/' '{print $1/$2}')
    
    # Determine if we need to convert frame rate
    local fps_filter=""
    if (( $(echo "$source_fps < 60" | bc -l) )); then
        # Use simple frame duplication for lower source FPS
        fps_filter="-vf fps=60"
    elif (( $(echo "$source_fps > 60" | bc -l) )); then
        # For higher source FPS, limit to exactly 60
        fps_filter="-vf fps=60"
    fi
    
    # Stream with appropriate settings based on source
    ffmpeg -re -stream_loop -1 \
        -i "$input_file" \
        -c:v libx264 \
        -preset medium \
        -b:v 8M \
        -maxrate 8M \
        -bufsize 16M \
        -g 60 \
        -keyint_min 60 \
        -sc_threshold 0 \
        $fps_filter \
        -r 60 \
        -c:a aac \
        -b:a 192k \
        -ar 48000 \
        -f flv \
        -loglevel info \
        "$rtmp_url"
}

# Parse command line arguments
while getopts "i:u:h" opt; do
    case $opt in
        i) INPUT_FILE="$OPTARG";;
        u) RTMP_URL="$OPTARG";;
        h) print_usage; exit 0;;
        ?) print_usage; exit 1;;
    esac
done

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "Error: ffmpeg is not installed"
    exit 1
fi

# Use provided video file or download sample
if [ -z "$INPUT_FILE" ]; then
    INPUT_FILE="$SAMPLE_VIDEO"
    if [ ! -f "$INPUT_FILE" ]; then
        echo "No input file specified, downloading high frame rate sample video..."
        if ! download_sample "$INPUT_FILE" "$SAMPLE_VIDEO_URL"; then
            exit 1
        fi
    else
        echo "Using existing sample video: $INPUT_FILE"
    fi
fi

# Main loop
echo -e "\nStarting continuous 60 FPS stream test..."
while true; do
    stream_to_rtmp "$INPUT_FILE" "$RTMP_URL"
    echo -e "\nStream ended, restarting in 2 seconds..."
    sleep 2
done 