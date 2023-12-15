#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = 'josh'
from setuptools import setup, find_packages
import os


# To install in development mode in virtualenv
# pip install -e .
setup(
    name='baseball_manager',
    version='0.3.4',
    author='Joshua Grigonis',
    author_email='josh.grigonis@gmail.com',
    packages=find_packages(),
    include_package_data=True,
    description='A baseball simulator',
    # TODO: these scripts don't work like I want
    scripts=[
        'scripts/compare_positions.py', 
        'scripts/create_many_players.py',
        'scripts/run_game.py',
    ],
    install_requires=[
    ],
    zip_safe=False,
)
