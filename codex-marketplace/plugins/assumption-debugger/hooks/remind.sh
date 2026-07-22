#!/bin/bash
cat >/dev/null
jq -n --arg message "$1" '{systemMessage: $message}'
