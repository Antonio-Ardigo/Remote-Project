"""
Quantum Hello World with Qiskit

This program creates a simple quantum circuit that demonstrates
fundamental quantum computing concepts:
- Superposition using a Hadamard gate
- Entanglement using a CNOT gate
- Measurement of quantum states

The circuit creates a Bell state |00> + |11>, meaning when measured,
both qubits will always be in the same state (both 0 or both 1).
"""

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.visualization import plot_histogram


def create_bell_state_circuit() -> QuantumCircuit:
    """Create a quantum circuit that produces a Bell state (entangled pair)."""
    qc = QuantumCircuit(2, 2)

    # Apply Hadamard gate to qubit 0 (creates superposition)
    qc.h(0)

    # Apply CNOT gate with qubit 0 as control and qubit 1 as target (creates entanglement)
    qc.cx(0, 1)

    # Measure both qubits
    qc.measure([0, 1], [0, 1])

    return qc


def run_simulation(circuit: QuantumCircuit, shots: int = 1024) -> dict:
    """Run the quantum circuit on the Aer simulator."""
    simulator = AerSimulator()
    result = simulator.run(circuit, shots=shots).result()
    counts = result.get_counts(circuit)
    return counts


def main():
    print("=" * 50)
    print("  Quantum Hello World with Qiskit")
    print("=" * 50)
    print()

    # Create the Bell state circuit
    circuit = create_bell_state_circuit()

    # Display the circuit
    print("Quantum Circuit (Bell State):")
    print(circuit.draw(output="text"))
    print()

    # Run on simulator
    print("Running on Aer simulator (1024 shots)...")
    counts = run_simulation(circuit)

    print()
    print("Measurement results:")
    for state, count in sorted(counts.items()):
        percentage = count / 1024 * 100
        bar = "#" * int(percentage / 2)
        print(f"  |{state}> : {count:4d} ({percentage:5.1f}%) {bar}")

    print()
    print("Expected: roughly 50% |00> and 50% |11>")
    print("This demonstrates quantum entanglement -- both qubits")
    print("are always measured in the same state!")
    print()
    print("Hello, Quantum World!")


if __name__ == "__main__":
    main()
