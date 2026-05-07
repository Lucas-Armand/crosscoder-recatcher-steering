# Crosscoder ReCatcher Steering Experiments

This repository contains an exploratory notebook for testing feature-level steering interventions in code-generation models.

The main goal is to investigate whether specific latent features can influence model behavior on programming tasks, especially in scenarios inspired by ReCatcher-style regression and code-quality experiments.

## Contents

- `recapher_crosscoder.ipynb`  
  Main experimental notebook, including:
  - environment setup
  - model loading
  - feature intervention experiments
  - code generation runs
  - basic evaluation and analysis

## Motivation

This work is part of an exploratory research direction on understanding how internal model representations affect code-generation quality, correctness, and regression-related behavior.

In particular, the notebook investigates whether modifying selected features can produce measurable changes in generated code.

## Requirements

The notebook was designed to run in a GPU environment such as Google Colab.

Main dependencies include:

```bash
pip install "transformers>=4.56.0" "accelerate>=1.8.0" "huggingface_hub>=0.34.0,<1.0" "bitsandbytes>=0.46.0"
pip install datasets scipy pandas tqdm
