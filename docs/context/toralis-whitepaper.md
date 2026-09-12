# Toralis Labs Whitepaper

*A Computational Infrastructure Company for 3D Anatomical Intelligence*

---

# Executive Summary

Toralis Labs is building foundational infrastructure to convert complex human anatomy into structured, machine-readable computational representations.

Our long-term vision is to enable any three-dimensional biological structure to be interpreted, modelled, and reasoned about by computers in a standardized, scalable way.

We are beginning with Endovascular Aneurysm Repair (EVAR) as our initial clinical case study because it is already commercialized, geometry-dependent, and economically sensitive to procedural inefficiencies. EVAR represents an ideal proving ground for demonstrating the power of anatomical computation.

Toralis Labs is not building another imaging viewer. We are building a computational translation layer between anatomy and intelligent systems.

---

# The Core Problem

Modern medicine generates highly detailed 3D imaging data. However:

- Most anatomical interpretation remains manual.
- Device sizing remains heuristic leading to increased operative times.
- Most AI models operate on 2D anatomy, reducing global understanding.

Current imaging systems are designed for human viewing, not machine reasoning.

As a result, decision-making in procedural medicine remains dependent on subjective interpretation rather than computational validation leading to increased errors, and wasted time in the operating theatre. 

---

# Vision

Toralis Labs aims to build a universal computational framework that transforms any 3D anatomy into a structured, machine-readable format that enables:

- Automated morphometric analysis
- Device–tissue interaction modeling
- Risk prediction
- Surgical planning assistance

Our thesis is: if we can make anatomy more AI-friendly, we can launch multiple products that serve a plethora of interventionists and surgeons in the niche cases they deal with. We can transform redundant medicine into an efficient practice. 

---

# Endovascular Aneurysm Repair (EVAR): Our First Application

Endovascular Aneurysm Repair (EVAR) is a minimally invasive procedure used to treat an abdominal aortic aneurysm (AAA), a pathological dilation of the abdominal aorta that carries a high risk of rupture and mortality.

Instead of performing open abdominal surgery (the previous status quo) to replace the diseased segment of the vessel, EVAR involves delivering a stent graft through the femoral arteries via small groin incisions. The graft is advanced under fluoroscopic guidance and deployed within the aneurysmal segment of the aorta. 

The stent graft acts as an internal scaffold, creating a new channel for blood flow and excluding the aneurysm sac from systemic arterial pressure. 

By redirecting blood flow through the graft, the aneurysm is decompressed, reducing the risk of rupture. In other words, we build a tunnel of blood flow to shrink the aneurysm. However, these stents do not seal properly. 

In fact, this study published in 2020 demonstrated that 51.9% of the study’s cohort required intraoperative fixes. These include sealing issues where blood leaks through the stent and the surgeon must adjust the stent according to the anatomy to prevent leakage. If we can analyze these preoperatively and in one scan tell the surgeons high-risk leakage areas, their time can be spared for more important cases. This improves efficiency for both the hospital and the surgeon. 

---

# Technology Background

Our co-founding team was previously working on https://radielhealth.com/, a CFD-grounded digital twin that aimed to provide clinicians additional information about the hemodynamic impact of surgical interventions. 

We’ve launched a new iteration of the model that allows a modular approach and will bridge our learnings into this new application. 

## Our Core Bread & Butter

We leverage a custom preprocessing pipeline that goes from `.msh` → `.pt` (PyTorch tensor format)

This enables us to extract:

- Node positions
- Vertex connectivity
- Mesh topology
- Ensures consistent numerical representation

We also then perform wall encoding which converts:

- Wall CSV → `.pt`
- Spatial alignment maintained between mesh nodes and WSS data

The mesh orientation is then normalized in 3D space and ensures rotational invariance control, consistent inferencing alignment and cross-mesh comparability. We leverage Graph Neural Networks to accomplish these tasks, allowing us to map 3D anatomy in our own method to run AI algorithms. 

## Our Training Method

We first ran 3D vascular models (VTP → MSH conversion) and meshing in, ParaView, ANSYS SpaceClaim and ANSYS Meshing. The output was a structured .msh file suitable for simulation. 

For each mesh:

We ran simulations run across Reynolds numbers 50–800. The following parameters were inputed. 

- Fluid model: **water (baseline incompressible fluid)**
- Flow type: **steady-state**
- Metric extracted: **Wall Shear Stress (WSS)**
- Convergence criteria:
    - Residuals to **1e-6 → 1e-5**
    - Lower residual → higher numerical convergence
- Runtime: ~6–7 hours per simulation set

Each Reynolds number produces:

- 1 wall data CSV
- ~18 CSV files per mesh
- Each CSV contains node-level WSS distributions across the geometry

This creates a structured CFD dataset mapping Mesh Geometry, Reynolds Number → Spatial WSS Distribution. 

> This replaces 6–7 hour CFD solves with near-instant neural inference.
> 

---

## Next Phase: Anatomy → Stent Geometry Matching

Previously, we’ve been exploring a shift:

Instead of only predicting WSS fields, we move toward Direct geometric compatibility modeling between anatomy and endovascular devices. We can extract the following:

- Proximal neck diameter
- Neck length
- Angulation
- Iliac taper
- Local curvature gradients
- Surface irregularity metrics

This ultimately allows us to look at a stent that is implanted into the patient, look at high risk seal zones and alert the clinician to ensure they act preoperatively and reduce intraoperative time. 

View a demo of our CFD prediction algorithm here:

Demotoralis.mp4

## The Market Size

- TAM: $902.6M USD
    - The total market size for digital twins.
- SAM: $135.9M USD
    - Most digital twins are pharmaceutical. We estimate 14% to be related to cardiac devices.
- SOM: $13.5M USD
    - We can target 10% of procedures that pertain to surgical devices to improve their testing.

## Business Model

We aim to charge with subscriptions to the device manufacturer, where they can provide it inclusive of their product. This will be preferred as surgeons can then utilise products that are known to be more efficient. We will charge $300 USD per procedure, with costs well under $100 per procedure. 

---

## Long-Term Expansion

While EVAR is our initial application, the core infrastructure is anatomy-agnostic.

Future applications include:

- Fenestrated and branched endografts
- Thoracic endovascular repair
- Peripheral arterial disease interventions
- Neurovascular stenting
- Transcatheter valve planning
- Pediatric vascular reconstruction
- Solid organ surgical planning
- Robotic procedural optimization

Our ultimate ambition is to create a standardized digital anatomy format that serves as the computational backbone of procedural medicine.

---

## Conclusion

Medicine currently treats anatomy as something to visualize.

Toralis Labs treats anatomy as something to compute.

By transforming 3D biological structures into structured, machine-readable systems, we aim to unlock simulation-driven precision across intervention.

EVAR is our starting point.

Computational anatomy is the destination.