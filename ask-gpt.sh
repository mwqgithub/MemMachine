#!/bin/bash

# 1. 将你的多行输入存储在一个变量中
#    使用 'read -r -d ''' 是最安全的方式，它能保留所有格式
read -r -d '' YOUR_PROMPT << EOF
给我一个在Windows上执行的bash脚本 安装pgvector 并且配置好postgresql 没有图形界面 没有docker 没有命令行交互 只在github action里面执行 这是docker配置 给我一个不用docker的版本 请注意我的环境里已经有chocolatey和winget了
docker run -d --name postgres \
  -e POSTGRES_USER=memmachine \
  -e POSTGRES_PASSWORD=mammachine_password \
  -e POSTGRES_DB=memmachine \
  -e POSTGRES_INITDB_ARGS="--encoding=UTF-8 --lc-collate=C --lc-ctype=C" \
  --network host \
  --health-cmd="pg_isready -U memmachine" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=5 \
  pgvector/pgvector:pg16
EOF

# 2. 使用 jq 来构建 JSON
#    -n:           表示 "null input" - 即不要从标准输入读取
#    --arg model "..." : 定义一个 jq 变量 $model
#    --arg input "$VAR": 定义一个 jq 变量 $input，其值来自 bash 变量 $YOUR_PROMPT
JSON_PAYLOAD=$(jq -n \
                  --arg model "gpt-5-pro" \
                  --arg input "$YOUR_PROMPT" \
                  '{model: $model, input: $input}')

# 3. 执行 curl 命令
#    注意 $JSON_PAYLOAD 变量必须用引号括起来
#    请将 YOUR_TOKEN_HERE 替换为你的真实 Token
curl https://api.chatanywhere.tech/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-dJwFK4eS9vTNTVJr7WLDIamK09mhcnsP4ZuJbJqsZToKeiHs" \
  -d "$JSON_PAYLOAD"