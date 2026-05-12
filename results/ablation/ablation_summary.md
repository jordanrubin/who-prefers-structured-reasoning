# Ablation Study Results

Which analytical skills drive the Condition C advantage?

**Design**: Each row removes one component from the 4-skill pipeline (inductify, negspace, excavate, antithesize).
Removing excavate also removes antithesize (dependency).

| Condition | n | Cross-Abstract | Epistemic Strat. | Falsifiability | Coverage | Assumption Surf. | Decision-Ready | COMPOSITE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A (naive) | 3 | 3.67 | 3.33 | 2.67 | 4.33 | 2.67 | 3.67 | 3.39 |
| C (full skills) | 3 | 4.67 | 4.67 | 3.67 | 5.0 | 4.67 | 4.0 | 4.45 |
| C−ind (no inductify) | 3 | 4.33 | 4.33 | 3.33 | 4.67 | 4.33 | 4.33 | 4.22 |
| C−neg (no negspace) | 3 | 4.67 | 4.67 | 3.33 | 4.0 | 4.33 | 5.0 | 4.33 |
| C−exc (no excavate+antithesize) | 3 | 4.33 | 4.33 | 3.67 | 4.67 | 5.0 | 4.33 | 4.39 |
| C−ant (no antithesize) | 3 | 3.67 | 3.67 | 2.67 | 4.33 | 3.67 | 4.0 | 3.67 |

## Interpretation

C − A delta: 1.06 composite points

**Component contributions** (drop from full C composite):
- Removing **inductify**: −0.23 composite
- Removing **negspace**: −0.12 composite
- Removing **excavate+antithesize**: −0.06 composite
- Removing **antithesize**: −0.78 composite
