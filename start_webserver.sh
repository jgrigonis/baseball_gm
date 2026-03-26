#!/bin/bash
uvicorn src.api.main:app --reload
# In production you would remove the --reload 
