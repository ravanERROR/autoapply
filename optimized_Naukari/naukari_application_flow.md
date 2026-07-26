# Naukari Modular Bot — Application Flow

This flow explains the 3-file bot structure:

- `naukari.py` — main bot runner
- `in_naukari.py` — handles Naukri internal apply and chatbot questions
- `externalapply.py` — handles company-site / external apply flow

```mermaid
flowchart TD
    A([Start Bot]) --> B[Run naukari.py]
    B --> C[Load personal.json config]
    C --> D{AI mode enabled?}

    D -- Yes --> E[Create Gemini AI client]
    D -- No --> F[Use manual prompt mode]
    E --> G[Start Chrome driver]
    F --> G[Start Chrome driver]

    G --> H[Open Naukri login page]
    H --> I[Login using Naukri credentials]
    I --> J{Login successful?}

    J -- No --> K[Stop bot and log login failure]
    J -- Yes --> L[Read search terms from config]

    L --> M[Build Naukri search URL]
    M --> N[Open search results page]
    N --> O[Collect job cards]
    O --> P{Any job cards found?}

    P -- No --> Q[Move to next search term]
    Q --> M

    P -- Yes --> R[Open one job card]
    R --> S[Read job title, company, job description]
    S --> T[Find Apply button]

    T --> U{Apply button found?}
    U -- No --> V[Mark failed / needs manual review]
    V --> W[Log result in failed CSV]
    W --> X{More job cards?}

    U -- Yes --> Y[Click Apply button]
    Y --> Z{Where did apply open?}

    Z -- Inside Naukri --> IA[Call in_naukari.py]
    Z -- Company website / external tab --> EA[Call externalapply.py]
    Z -- Already applied --> AA[Mark already_applied]

    IA --> IB[Detect Naukri chatbot questions]
    IB --> IC{Question found?}
    IC -- No --> ID[Check success message]
    IC -- Yes --> IE[Search exact question in config/questions.json]

    IE --> IF{Answer found?}
    IF -- Yes --> IG[Fill saved answer]
    IF -- No --> IH{AI mode enabled?}

    IH -- Yes --> II[Ask Gemini for best answer]
    IH -- No --> IJ[Show manual popup and ask user]

    II --> IK{AI returned answer?}
    IK -- Yes --> IL[Fill AI answer]
    IK -- No --> IJ[Show manual popup and ask user]

    IJ --> IM[Save user answer to config/questions.json]
    IM --> IN[Fill manual answer]

    IG --> IO[Submit answer]
    IL --> IO[Submit answer]
    IN --> IO[Submit answer]

    IO --> IB
    ID --> IP{Applied successfully?}
    IP -- Yes --> IQ[Mark applied]
    IP -- No --> IR[Mark needs_manual_review]

    EA --> EB[Switch to external company website tab]
    EB --> EC{Multiple job cards/listings visible?}
    EC -- Yes --> ED[Fuzzy match same job title/company]
    EC -- No --> EE[Continue on current job page]

    ED --> EF[Click matching external job card]
    EE --> EG[Find Apply / Apply Now button]
    EF --> EG

    EG --> EH{External apply button found?}
    EH -- No --> EI[Mark external_needs_manual_review]
    EH -- Yes --> EJ[Click external Apply button]

    EJ --> EK{Login / CAPTCHA / OTP / account creation required?}
    EK -- Yes --> EI[Mark external_needs_manual_review]
    EK -- No --> EL[Detect form fields]

    EL --> EM[Fill common fields from personal.json]
    EM --> EN[Upload resume if file input exists]
    EN --> EO[Detect custom questions]

    EO --> EP{Question exists in questions.json?}
    EP -- Yes --> EQ[Fill saved answer]
    EP -- No --> ER{AI mode enabled?}

    ER -- Yes --> ES[Ask Gemini]
    ER -- No --> ET[Ask user manually]
    ES --> EU{AI answer available?}
    EU -- Yes --> EV[Fill AI answer]
    EU -- No --> ET[Ask user manually]

    ET --> EW[Save answer to questions.json]
    EW --> EX[Fill manual answer]

    EQ --> EY[Continue form]
    EV --> EY[Continue form]
    EX --> EY[Continue form]

    EY --> EZ{external_auto_submit true?}
    EZ -- No --> FA[Stop before submit for manual review]
    EZ -- Yes --> FB[Click Submit / Send Application]

    FB --> FC{Submitted successfully?}
    FC -- Yes --> FD[Mark external_applied]
    FC -- No --> FE[Mark external_needs_manual_review]

    AA --> LG[Log result in applied CSV]
    IQ --> LG[Log result in applied CSV]
    IR --> W
    EI --> W
    FA --> W
    FD --> LG
    FE --> W

    LG --> X{More job cards?}
    X -- Yes --> R
    X -- No --> YN{More search terms?}

    YN -- Yes --> M
    YN -- No --> END([Stop Bot])
    K --> END
```

## Short execution summary

1. `naukari.py` starts the bot, loads config, starts Chrome, logs in to Naukri, searches jobs, and opens each job card.
2. When the apply button opens an internal Naukri flow, `naukari.py` sends control to `in_naukari.py`.
3. `in_naukari.py` handles Naukri chatbot questions using `config/questions.json`, Gemini AI, or manual popup answers.
4. When the apply button opens a company website, `naukari.py` sends control to `externalapply.py`.
5. `externalapply.py` searches the external page for the matching job, clicks Apply, fills forms, uploads resume, answers questions, and submits only when allowed by config.
6. Every result is logged into applied or failed CSV files.
```
