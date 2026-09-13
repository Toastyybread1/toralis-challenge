# Show the results to teammates

Double-click `Show-Team-Review.cmd`, or open `outputs/team_review/index.html` in a browser.
To use another computer, copy `outputs/team_review.zip`, extract it, and open its index.
No Python, server, source CT volumes or model weights are needed for viewing.

## Five-minute walkthrough

1. Explain the CT and aorta-only mask: daughters are not in the supplied mask.
2. Show case 19 and the six processing steps on the overview page.
3. Show case 21: three draft matches, two unmatched counted groups, and one
   deferred candidate with a separate return-path montage.
4. Show case 20's miss and case 24's correctly loaded coverage.
5. Explain that 18/19 is development agreement on five draft-labelled cases.
   The other 20 cases have no daughter accuracy measurement. No anatomy is signed off.

Cyan is the supplied aorta border; yellow is a draft daughter outline where
available; red is an origin; magenta is in-slice path evidence. Five slices in
each of three planes are shown. This is a static CT review, not a full 3D volume
renderer or clinical annotation application.

All 132 retained groups and one deferred group are visible in 135 montages,
including return-connection evidence and case-24 coverage. Each case links its
detailed prediction evidence and review record.

Rebuild using `.venv\Scripts\python.exe tools/build_team_review.py` from the
repository root. This copies existing evidence without rerunning detection.
