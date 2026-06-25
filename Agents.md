{\rtf1\ansi\ansicpg950\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # AGENTS.md\
\
## Project goal\
\
Build a Discord bot for the podcast \uc0\u12300 \u24341 \u26360 \u24215 \u12301 .\
\
The bot should:\
1. Monitor the podcast RSS feed.\
2. Download new podcast episodes.\
3. Transcribe audio locally.\
4. Generate transcript Markdown files for Obsidian.\
5. Generate structured episode summaries.\
6. Extract book mentions, concept mentions, topics, timestamps, and relationship data.\
7. Build a searchable index.\
8. Let Discord users ask:\
   - Has the host introduced books about a certain topic?\
   - Did the host mention a certain idea in any episode?\
   - Which episode mentioned a specific book, topic, or concept?\
   - What books are related to a concept?\
\
## Core architecture\
\
Obsidian is the source of truth for long-term knowledge.\
\
Discord bot is only the query and interaction interface.\
\
Pipeline:\
\
RSS\
\uc0\u8594  audio download\
\uc0\u8594  local transcription\
\uc0\u8594  Obsidian Markdown export\
\uc0\u8594  structured summary and index\
\uc0\u8594  Discord query interface\
\
## Tech stack\
\
- Python 3.12\
- discord.py\
- feedparser\
- SQLite\
- faster-whisper for local transcription\
- Markdown files for Obsidian\
- YAML frontmatter for metadata\
- python-dotenv for secrets\
\
## Obsidian vault rules\
\
Generated files should be written only to these folders unless explicitly requested:\
\
- Podcast/\uc0\u24341 \u26360 \u24215 /transcripts/\
- Podcast/\uc0\u24341 \u26360 \u24215 /episodes/\
- Inbox/Podcast Import/\
- Inbox/Podcast Import/Draft Book Cards/\
- Inbox/Podcast Import/Draft Concept Cards/\
\
Never modify existing personal notes outside these folders.\
\
Do not overwrite existing notes. If a file already exists, append an `## Update Log` section or create a new draft file.\
\
## Markdown note types\
\
Generate these note types:\
\
1. Transcript note\
2. Episode summary note\
3. Draft book card\
4. Draft concept card\
\
## Transcript note requirements\
\
Transcript notes should:\
- Preserve timestamps.\
- Include episode metadata in YAML frontmatter.\
- Link back to the episode note.\
- Avoid unnecessary summarization.\
\
## Episode summary note requirements\
\
Episode notes should include:\
\
- One-sentence summary\
- Key points\
- Mentioned books\
- Mentioned concepts\
- Topics\
- Book mention levels\
- Concept relationships\
- Important timestamps\
- Suggested user questions\
- Link to full transcript\
\
## Book mention levels\
\
Use these categories:\
\
- main_focus: the book is the main focus of the episode\
- discussed: the book is discussed in detail\
- referenced: the book is cited or used as support\
- passing_mention: the book is only briefly mentioned\
\
## Concept relationship types\
\
Use these relationship types:\
\
- leads_to\
- contrasts_with\
- supports\
- criticizes\
- expands_on\
- example_of\
- precedes\
- influences\
- similar_to\
\
## Query behavior\
\
Discord bot should answer conservatively.\
\
When answering user questions, it should:\
1. Search structured episode notes, book cards, and concept cards first.\
2. Use transcript chunks only as evidence.\
3. Include episode title and timestamp when possible.\
4. Clearly say when something was only briefly mentioned.\
5. Never imply the podcast fully summarized a book unless the episode actually focused on that book.\
\
## Initial milestones\
\
1. Create a minimal Discord bot with `/ping`.\
2. Add RSS parsing.\
3. Add SQLite episode storage.\
4. Add audio downloader.\
5. Add local transcription.\
6. Export Obsidian transcript notes.\
7. Export episode summary notes.\
8. Extract book and concept indexes.\
9. Add `/episodes`, `/book`, `/topic`, and `/mentioned` commands.\
10. Add search over summaries and transcripts.\
\
## Development rules\
\
- Make small changes.\
- Do not implement multiple milestones at once unless requested.\
- Keep secrets in `.env`.\
- Never commit Discord tokens, API keys, or private vault paths.\
- Explain changed files after each task.\
- Add tests where practical.}