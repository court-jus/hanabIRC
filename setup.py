from distutils.core import setup
from setuptools import find_packages

setup(
    name='HanabIRC',
    version='0.1.2',
    packages=find_packages(exclude=['*test']),
    license='FreeBSD License', 
    author='Geoff Lawler', 
    author_email='phil.s.stein@gmail.com',
    description='An IRC bot that organizes and plays the card game Hanabi.',
    long_description=open('README.txt').read(),
    url='https://github.com/philsstein/hanabIRC',
    install_requires=['irc'],
    scripts=['bin/hanabIRC']
)
