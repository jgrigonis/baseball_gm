#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = 'josh'
from setuptools import setup, find_packages
import os

version = '0.1'
here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

setup(
    name='baseball_gm',
    version='0.1',
    author='Joshua Grigonis',
    author_email='josh.grigonis@gmail.com',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    description=('A baseball simulator'),
    install_requires=[],
    zip_safe=False,
    )
