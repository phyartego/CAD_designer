---
name: consumer-cad
description: Design consumer electronics enclosures and small assemblies, generate CAD files, measure geometry and check hinge motion using the consumer-cad MCP or local CLI. Use for PCB, battery, enclosure, bracket and assembly revisions.
---

# Consumer electronics design

Record units, source of dimensions, mounting datums and parts that must remain fixed. Treat a vendor envelope, PCB outline and nominal cell thickness as separate inputs. Explicitly mark estimates. When a new mechanism changes assembly or service access, describe how it installs and opens.

For a split metal rear cover, call `enclosure_defaults` and change only the requested fields. The battery and PCB stay on the chassis. Use `check_enclosure` to get axis-aligned dimensions, named clearances, overlap volumes, part names and sampled opening angles. Reproduce an issue by retaining the input parameters. Use `optimize_enclosure_height` when changing body height is allowed. Re-run the check on the returned parameters. Preserve locked dimensions and report any issue that remains under the supplied bounds.

For another form factor, call `solid_schema` and describe each manufactured component in local coordinates. Apply its installed pose and identify moving parts before calling `check_custom`. For freeform geometry beyond the JSON features, a local coding agent can write a trusted build123d Python recipe. Start with `examples/desktop_stand.py`, implement `build(parameters)`, and run `consumer-cad recipe path/to/design.py --out path/to/new-run --freecad`. On a remote client use JSON tools, or hand off an appropriate Python recipe for local execution.

Export the chosen design with `build_enclosure` or `build_custom`. Set `freecad=true` when the request requires an FCStd. Inspect `passed`, dimensions and the returned artifact list. Use `preview_run` to inspect the actual drawing, and `read_run` to revisit a saved run. Return output paths on the machine running CAD. Remote clients can use `read_artifact` with an artifact key or a BOM part path and combine base64 chunks in offset order.

State the measured gap or interference that drove each change, the revision's input, the angular interval/step and the exported files. Sampled rigid-body checks establish feasibility at the listed poses. Report tolerance stacks, deformation, contact forces or manufacturing details separately when those require measurements or additional simulation.
