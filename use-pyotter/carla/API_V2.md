(Internal file only)

### Toolchain image

Produce one container toolchain image with all the required deps to run CARLA on USC CARC. This should be uploaded as a toolchain image to the GitHub repo.


### Scenario Library

Since we will be rolling many scenarios for the projects, we should come up with a source control system to keep a scenario library. I suggest storing them all on Huggingface. The sha256 of each scenario .json.gz file can be its unique "fingerprint". All telemetry files need to link to this fingerprint so we can re-run scenarios deterministically, or see the contents and conditions of the scenario.

### Results Library

All telemetry results will also go to hf. 

### CARC runner

Running on CARC should be as easy as possible. This is close to the dream API usage:

```
cd use-pyotter/

uv sync
uv run carla-server 

# (wait for the server to be up)

uv run otter-drive {{scenario_id}}
# reports the batch slurm job id that is queued

# watch the logs
tail -f logs/{{batch job id}}

# the results are automatically uploaded to hf when done and stored locally on the user's carc node
```


