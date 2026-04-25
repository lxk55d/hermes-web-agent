"""Hermes Web Agent — 通过浏览器操控LLM网页版完成任务的工具包"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="hermes-web-agent",
    version="0.1.0",
    description="让AI Agent通过浏览器操控LLM网页版（ChatGPT/Claude/DeepSeek）完成任务",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Hermes Web Agent Contributors",
    url="https://github.com/your-username/hermes-web-agent",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "playwright>=1.40.0",
        "pillow>=10.0.0",
        "httpx>=0.25.0",
    ],
    extras_require={
        "mcp": ["mcp>=1.0.0"],
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.23"],
    },
    entry_points={
        "console_scripts": [
            "hermes-web-agent=hermes_web_agent.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
