# Quantum Hello World with Qiskit

A quantum computing "Hello World" project using IBM's [Qiskit](https://qiskit.org/) framework.

## What's Inside

| File | Description |
|---|---|
| `hello_quantum.py` | Standalone Python script — creates a Bell state and runs it on a simulator |
| `hello_quantum.ipynb` | Jupyter notebook — interactive walkthrough of superposition, entanglement, and measurement |
| `requirements.txt` | Python dependencies for the Qiskit quantum environment |

## Quick Start

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the Python script
python hello_quantum.py

# Or launch the Jupyter notebook
jupyter notebook hello_quantum.ipynb
```

## Requirements

- Python 3.11+
- pip

## Concepts Covered

- **Superposition** — Hadamard gate puts a qubit into a mix of |0⟩ and |1⟩
- **Entanglement** — CNOT gate links qubits so their measurements always correlate
- **Bell State** — The simplest entangled state: |00⟩ + |11⟩
- **GHZ State** — Three-qubit entanglement (notebook only)
- **Simulation** — Running quantum circuits on the Aer simulator
