#!/usr/bin/env bash
# NexAgent derleme (Linux/macOS): ./build.sh [rid]   örn: linux-x64
set -e
RID="${1:-linux-x64}"
dotnet publish -c Release -r "$RID" --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o "../build/agent/$RID"
