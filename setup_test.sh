#!/bin/bash

# Create test directory
mkdir -p test/sample_videos

# Download a sample video if not exists
if [ ! -f test/sample_videos/sample.mp4 ]; then
    wget -O test/sample_videos/sample.mp4 https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4
fi 