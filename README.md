# Detecting Sentiment in Micro-Community Vernacular #

## Project Overview ## 
This is a research project which aims to develop a model appropriate for detecting the sentiment of micro-community vernacular. 
Essentially, it's been noted that internet culture is shifting away from large forum based platforms, towards smaller gate-kept
micro-communities in what's often referred to as the "Cosy Web". These communities develop their own vernacular through shared experiences
and values which cannot be easily understood outside the context of the community. A discord server is the perfect example of a micro-community.
Servers develop their own specific in jokes, stickers etc that can only be understood by the server members. 
Sentiment analysis is a NLP and AI technique used to identify, extract, and quantify the emotional tone, attitude, or opinion behind text. 

Essentially I want to leverage sentiment analysis to correctly identify and classify the emotional tone of micro-community slang. To achieve this
I have exported a dataset of over 540,000 messages from my friend groups discord server (with consent) in the hopes of training an NLP model. Currently
I am at the data cleaning/preparation stage. I will be updating this document consistently with progress reports alongside pushes to the repository so don't
be afraid to check back!

I have described the various files in this repo below if anyone would like to make use of the data pipeline for their own projects. 

### Bonus Goal
I would eventually love to use these findings and pipelines to create a Discord Bot that others could use to accurately determine the mood of their
server over time. 

## TLDR ##
Is this Discord server sticker happy or sad <br>
<img width="160" height="160" alt="image" src="https://github.com/user-attachments/assets/2b194b93-7867-4bab-a34e-750d0eadb277" /> 

## Files
- Discord_Extractor.py: This script makes calls to discord message API to return message objects which are outputted to a JSONL file
  - Requires discord bot with read message history and view channel permission
  - Store bot auth token within .env file (see .env.example)
  - Script requires argument(s) in terminal: run --help alongside script in terminal for more information
    - Mandatory: channel id's of channels you want exported
    - Optional: output directory, id of the most recent message you don't want exported
- Logger.py: A small wrapper around Python's logging module that sets up consistent, readable logs for the project's scripts.
- Discord_Preprocessing.py: reads JSONL outputs into a secure clean analyzable PANDAS data frame
  - Performs HMAC hashing on author id to protect anonymity in event of data leak
  - Performs pseudonymization through mass replacement of author id and plain text names (including common mispellings) in content  
  - Stores data directory, HMAC key and local path to lookup dictionary in .env file (see .env.example)
- .env.example: example .env file illustrating the types of information called by the exporter/pre-processing script during runtime
  - DISCORD TOKEN: the token for your discord bot
  - DATA-DIRECTORY: the file path where your exported message data is stored
  - HASH_KEY: generate a hash key with secrets module and store it here (required for keyed HMAC hashing of user id's)
  - Pseudonym_dict: this is the path to a JSON file that contains key value pairs of user ID and pseudonym.
    - I have an example in this repo but I suggest keeping yours on a different path
