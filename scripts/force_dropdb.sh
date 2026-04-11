#!/bin/bash
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'your_db_name';" postgres


psql -c "DROP DATABASE baseball_manager;"
psql -c "CREATE DATABASE baseball_manager;"
