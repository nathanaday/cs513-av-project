**Project Title**

Yonsoo Kim, Nathan Aday, Tomohiko Uemura, Rachel Lin, Jeslyn Yang, Illy Hoang

**Purpose**

- Build a scheduler that switches between two perception paths. The Nano path (small model, low FPS) runs on quiet roads, and the Heavy path (large model, high FPS) runs in busy or risky conditions.  
- Answer problem statement: how fast and how accurately can low-power mode wake the Heavy model when something unexpected happens?

**Task Breakdown**

- Decide on simulator by early October. Pin environments so runs reproduce across machines. Build the latency-faithful loop that holds each action back by its model's inference time.  
- Profile accuracy and latency on simulator frames. Freeze a fixed latency profile for each path.  
- Build the trigger. Measure wake-up latency, missed anomalies, and false alarms, since false alarms waste compute. Plot the trade-off curve.  
- Implement and tune thresholds. Define fallback behavior (when uncertain, go Heavy and slow down). Handle edge cases like an anomaly arriving mid-switch.  
- Build the logging pipeline and statistical comparison. Take measured power readings on one reference machine only. Produce figures and the side-by-side demo dashboard.  
- Implement online monitors and run the falsification campaign. Report counterexamples before and after fixes, plus scenario coverage.

**Schedule**  
	

| Dates | Milestones |
| :---- | :---- |
| Sep 21 | Project pitch due |
| Sep 22 – Oct 4 | Simulator shortlisted and tested on all machines; specs, metrics, and model candidates defined; simulator of-choice is decided by |
| Oct 5 – Oct 18 | Both perception paths, anomaly trigger, and mode state machine working independently |
| Oct 19 – Nov 1 | End-to-end loop running; always-Heavy baseline measured; check-in demo (date TBA) |
| Nov 2 – Nov 15 | Falsification campaign; counterexamples fixed; scheduler refined |
| Nov 16 – Nov 29 | Final runs, figures, demo dashboard, video  |
| Nov 30 / Dec 1 | 5-min video uploaded / demo day |
| Dec 10 | 15-page final report due |

**Expected Outcome**  
The project is successful if the scheduler uses less compute and energy and still reaches the goal with safety no worse than always-Heavy (collisions, minimum TTC, spec violations). This must hold across easy scenarios (open highway with a sudden anomaly) and hard ones (dense urban).

**Resources Required**  
Hardware:

- Team laptops, including Apple Silicon MacBooks. 16 GB+ memory is recommended, since each machine runs the simulator and two models at once.  
- One reference machine. All official latency and power measurements come from this single machine so results stay comparable.  
- USC CARC cluster access for large batches of falsification runs later in the semester.

Software:

- A cross-platform driving simulator that meets the requirements checklist: runs on Apple Silicon, renders camera images, and supports scripted scenarios.  
- A deep learning framework that runs on both Apple Silicon and NVIDIA GPUs like TF  
- A pretrained object detector family with small and large variants for the Nano and Heavy paths  
- An STL monitoring library for runtime specification checks.  
- A scenario generation and falsification tool compatible with the chosen simulator.  
- Compute profiling tools for FLOPs counting and per-platform power measurement.  
- Shared infrastructure: a Git repository, a pinned environment manager, and Python for logging and plotting.

**Literature Survey**  
\<Give a list of at least 3 papers/reports/blogposts/websites that you surveyed to prepare the proposal\>  
