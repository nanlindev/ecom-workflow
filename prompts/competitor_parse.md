---
version: competitor_parse-v1
model: deepseek-chat
output_format: json
---
Extract product price data from competitor page text or HTML snippet.

Return ONLY valid JSON:

{
  "price": <number or null>,
  "currency": "<ISO currency or null>",
  "title": "<product title or null>",
  "in_stock": <true|false|null>,
  "fallback_used": false
}

URL: {url}
Raw content:
{raw_content}
