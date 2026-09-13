# BranchForge Spatial

Phone-friendly live 3D + AR companion to the BranchForge 3D Slicer extension.

Production: https://branchforge-ar.vercel.app

See [the complete setup, privacy and platform guide](../docs/AR_VIEWER.md).

```text
npm ci
npm test
npm run build
npm run dev
```

Deploy only this subdirectory, never the medical-data repository root. All publisher keys and Redis credentials stay server-side or in ignored local files. The browser uses an expiring read capability from the QR code.
