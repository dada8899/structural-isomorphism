from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="structural-isomorphism",
    version="0.4.0",
    author="Qihang Wan",
    description="Cross-domain structural similarity search engine + SOC validation pipeline",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dada8899/structural-isomorphism",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        # Core engine
        "sentence-transformers>=2.0",
        "numpy",
        "torch",
        # Statistical / data processing (used by phase detector, validation,
        # tutorial reproductions, and the active-learning simulation)
        "scipy",
        "pandas",
        "powerlaw",
        "requests",
        "matplotlib",
    ],
    extras_require={
        "demo": ["gradio>=4.0"],
        "tutorials": ["jupyter", "matplotlib", "powerlaw"],
        "dev": ["scikit-learn", "pytest", "black", "ruff"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    package_data={
        "structural_isomorphism": ["data/*.jsonl"],
    },
    entry_points={
        "console_scripts": [
            "v4=v4.cli:main",
        ],
    },
)
