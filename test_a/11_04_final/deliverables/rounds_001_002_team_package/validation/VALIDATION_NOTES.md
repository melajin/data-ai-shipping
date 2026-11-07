# Delivery validation

The first packaging replay used the round002 venv (pandas 3.1.0), and failed the round001 default-CSV equality assertion before any model prediction. Round001 originally used pandas 2.2.3. The verification requirements and version check now explicitly pin pandas 2.2.3. This is a packaging environment correction, not a changed experiment or training run.

Final local verification uses the existing Python 3.13.3 base environment (pandas 2.2.3 / numpy 2.2.5 / LightGBM 4.7.0), with the existing round002 site-packages appended for CatBoost 1.2.10. No new packages were installed, and no training was run. This is not a clean-machine installation test. See model_replay.json for versions and measured deltas. Bootstrap intervals were not recalculated.
