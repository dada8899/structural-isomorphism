from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="structural-isomorphism",
    version="0.1.0",
    author="Qihang Wan",
    description="Cross-domain structural similarity search engine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/structural-isomorphism",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "sentence-transformers>=2.0",
        "numpy",
        "torch",
    ],
    extras_require={
        "demo": ["gradio>=4.0"],
        "dev": ["scikit-learn", "pytest"],
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
)
