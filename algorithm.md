# Journal Review Time Extraction Algorithm

Below is the flowchart detailing the algorithm used to extract and process paper statistics, formatted for a methodology section using generalized variables.

**Inputs:**
* $J$: Set of Target Journals
* $N$: Required Paper Samples per Journal
* $Y_{start}, Y_{end}$: Target Publication Date Range (journal publication year)

**Outputs:**
* $D$: Dataset with, per paper, the review time $t_{review} = t_{accept} - t_{receive}$ when the journal reports it, and the proxy $t_{proxy} = t_{publish} - t_{arXiv}$
* Per-journal summary: sample size, number of measured papers, median and interquartile range

**Date sources, in order of trust:**
1. Crossref article history ($t_{receive}$, $t_{accept}$ deposited by the publisher; Springer and Wiley do this)
2. First page of the arXiv PDF ("Manuscript received ...; accepted ..." footnote; common for IEEE journals)
3. None: only $t_{proxy}$ is available

```mermaid
flowchart TD
    Start([Start Procedure]) --> Init[Initialize Dataset D as empty<br/>Load cache C of resolved papers]

    Init --> LoopJ{For each Target Journal j in J}
    LoopJ -- Next --> InitParams[Set Valid Count v = 0<br/>Set Query Offset q = 0<br/>Set Fetch Attempts a = 0]

    InitParams --> CheckLimits{Is v < N<br/>AND<br/>a < Max Attempts?}

    CheckLimits -- Yes --> API[Query arXiv API<br/>journal reference = j, offset q]
    API --> RateLimit{Rate Limit<br/>Encountered?}
    RateLimit -- Yes --> Backoff[Apply Exponential Backoff<br/>Wait w seconds]
    Backoff --> API
    RateLimit -- No --> Sleep[Fixed Delay for<br/>Throttle Compliance]

    Sleep --> LoopP{For each paper p<br/>in the batch}

    LoopP -- Next Paper --> HasDOI{Does p have a DOI?}
    HasDOI -- Yes --> Crossref[Look up DOI in Crossref<br/>venue, t_publish, t_receive, t_accept]
    Crossref --> Venue{Venue == j<br/>AND t_publish within<br/>Y_start..Y_end?}

    Venue -- Yes --> Dated{Crossref has<br/>t_receive and t_accept?}
    Dated -- No --> PDF[Read first page of arXiv PDF<br/>Match received / accepted dates]
    PDF --> Compute
    Dated -- Yes --> Compute[Compute t_review = t_accept - t_receive<br/>Compute t_proxy = t_publish - t_arXiv]

    Compute --> Usable{0 < t_review ≤ 5 years<br/>OR t_proxy > 0?}
    Usable -- Yes --> KeepPaper[Append p to Journal Dataset<br/>Increment Valid Count v++]

    KeepPaper --> QuotaMet{Is v == N?}
    QuotaMet -- Yes --> Save[Append Journal Dataset to D<br/>Persist cache C]
    QuotaMet -- No --> LoopP

    Usable -- No --> LoopP
    Venue -- No --> LoopP
    HasDOI -- No --> LoopP

    LoopP -- End of Query Batch --> StepOffset[Increment Offset q<br/>Increment Attempts a++]
    StepOffset --> CheckLimits

    CheckLimits -- No --> Save
    Save --> LoopJ

    LoopJ -- Done --> Visualize[Per journal: median and IQR of t_review and t_proxy<br/>Grouped box plots, measured vs proxy<br/>Tabular index view and CSV export]
    Visualize --> End([End Procedure])
```

**Notes for the methodology section:**
* The venue check against Crossref is required because arXiv's journal-reference search matches phrases, so a query for *Robotics and Autonomous Systems* also returns *Annual Review of Control, Robotics, and Autonomous Systems*.
* $t_{publish}$ is the Crossref online publication date, falling back to the DOI registration date (IEEE registers the DOI at Early Access).
* $t_{proxy}$ is reported separately and never mixed with $t_{review}$. Authors who post to arXiv after acceptance give a short or negative proxy, so it is a rough bound, not a review time.
* Papers are sampled most recent first (arXiv submission date, descending), so each journal's sample is its latest $N$ usable papers.
