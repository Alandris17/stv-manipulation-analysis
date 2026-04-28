# STV Manipulation Analysis

This project analyzes the susceptibility of elections to coalitional manipulation under the Rule-13 Single Transferable Vote (STV) system.

It includes a full Python implementation that parses real election data, computes outcomes, and searches for the smallest group of voters that can strategically alter the result.

---

## Features

* Parses **PrefLib `.toi` files** (including ties and truncated ballots)
* Implements **Rule-13 STV** (parallel elimination of lowest-scoring candidates)
* Computes the **truthful election outcome**
* Searches for **smallest manipulating coalition**
* Supports configurable parameters via command-line interface

---

## What is Coalitional Manipulation?

A group of voters can *manipulate* an election if they can change their votes strategically to obtain an outcome they all strictly prefer over the truthful result.

This project searches for:

* A target candidate
* A coalition of voters
* A strategic ballot

such that the new election outcome is strictly better for all members of the coalition.

---

## Requirements

* Python 3.7+
* No external dependencies (standard library only)

---

## Usage

Run the script with a PrefLib `.toi` file:

```bash
python aspen_stv_manip.py aspen_2009.toi
```

### Optional arguments

```bash
--kmax 500       # Limit maximum coalition size
--debug          # Enable debug output
```

Example:

```bash
python aspen_stv_manip.py aspen_2009.toi --kmax 500 --debug
```

---

## Example Output

```
=== Truthful STV (Rule-13) result ===
Winner: Candidate X

=== Searching for coalitional manipulation ===
[FOUND] Better manipulation for Candidate Y at k=17!

=== Manipulation found ===
Target candidate: Candidate Y
Smallest coalition size found: 17
```

---

## Project Structure

* `aspen_stv_manip.py` — main script (parser, STV, manipulation search)
* `aspen_2009.toi` — election dataset (PrefLib format)

---

## Dataset

The dataset is sourced from **PrefLib**, a library of real-world preference data:

* Aspen 2009 City Council Election

---

## Methodology

* STV implemented using Rule-13 elimination
* Fractional vote splitting for tied rankings
* Greedy heuristic search for manipulation:

  * Prioritizes strongest losing candidates
  * Builds minimal coalition iteratively
  * Verifies preference improvement for all voters

---

## Notes

* The manipulation search uses heuristics — it is not guaranteed to find all possible manipulations
* Performance depends on the `--kmax` parameter and election size

---

## Why This Matters

Understanding manipulation in voting systems is essential for evaluating their fairness and robustness.

This project demonstrates how even real-world elections may be vulnerable under coordinated strategic behavior.
