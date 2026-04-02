#!/bin/bash
source .venv/bin/activate
uvicorn src.api.main:app --reload
# uvicorn src.api.main:app
# In production you would remove the --reload 
