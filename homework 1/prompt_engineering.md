# Prompt Engineering Experiments — Homework 1

## Experiment setup

- Date: October 27, 2026.
- Model selected by the student: OpenAI GPT-4o-mini in OpenRouter Chat.
- Each prompt was submitted in a new chat, using the same selected model.
- Evidence: actual responses copied by the student into the project discussion.
- These are direct model experiments, separate from the resume app's routing.
- One response per condition was collected. Parameters were not recorded; these
  small comparisons do not establish statistically reliable improvements.

## 1. Role Prompting

### Concept and lecture reference

Role prompting assigns a persona to guide a response. The lecture presents this
in slides 27–28 of AI Agents_prompt_engineering.pptx.

### Prompts tested

Baseline, without a specified role:

```text
Explain what an API is.
```

With a role and audience:

```text
You are a teacher explaining programming to a beginner. Explain what an API is.
```

### Actual observations

The baseline response was a long technical explanation. It covered endpoints,
GET/POST/PUT/DELETE, responses and status codes, authentication, rate limiting,
interoperability, modularity, and several API applications.

The role-based response used simpler framing, including a bridge analogy, a
weather-app request/response example, and a restaurant-waiter analogy. It omitted
much of the baseline's HTTP-method and authentication detail. It still used JSON,
XML, and modularity without fully explaining them.

### Effectiveness and limitations

For this comparison, the role-and-audience instruction made the answer more
approachable, but it did not remove all technical terms or make the answer very
short. The prompt changed both persona and audience, so the difference cannot be
attributed to persona alone. Both responses concentrated on web-style APIs; URLs
and HTTP are not requirements for all APIs. The waiter analogy also simplifies
implementation details. A more accessible style does not by itself prove better
technical accuracy.

### Connection to the homework

The resume application's experts have different roles and instructions in
llm_roles. A role can steer a response toward SQL, Python, or a content answer,
but our earlier malformed plans show that role instructions do not guarantee
correct syntax.

## 2. Style Prompting

### Concept and lecture reference

Style prompting specifies a tone or presentation style. The lecture presents it
in slides 29–30.

### Prompts tested

Baseline:

```text
Write a message telling my team that the meeting has moved to Friday.
```

With an explicit style:

```text
Write a casual, friendly message with emojis telling my team that the meeting has moved to Friday.
```

### Actual responses

Baseline message, excluding the model's introductory and closing commentary:

```text
Subject: Change of Meeting Date

Hi Team,

I wanted to let you all know that our meeting has been moved to Friday.
Please update your calendars accordingly.

Thank you for your understanding!

Best,
[Your Name]
```

With the style instruction:

```text
Hey team! 😊
Just wanted to give you a quick heads up that our meeting has been moved to Friday! 🗓️ Please mark your calendars! Let me know if you have any questions.
Looking forward to seeing everyone then! 👍
Cheers!
```

The original responses used Markdown emphasis around Friday; it is omitted in
these plain-text excerpts.

### Effectiveness and limitations

The baseline used an email subject, polite wording, and a signature placeholder.
The styled response used an informal greeting, conversational wording, emojis,
and no subject line. Both retained the key fact that the meeting moved to Friday.
The instruction visibly changed the requested style in this one comparison;
it did not test nuanced styles or demonstrate a general accuracy improvement.

### Connection to the homework

Style instructions can shape the final user-facing synthesis. They should not
add conversational prose to an expert whose output must be executable SQL or
Python. In the write flow, preserving the exact outcome message remains required.

## 3. Few-shot Prompting

### Concept and lecture reference

Few-shot prompting supplies examples that illustrate the expected mapping from
input to output. It is introduced in slide 9 and discussed in slides 33–41.

### Zero-shot prompt

```text
Classify each review as Positive or Negative. Return one label per line.

1. Not bad at all, actually.
2. Great, another two hours of my life I'll never get back.
```

Actual response, displayed inside a Markdown code block by the model:

```text
Positive
Negative
```

### Few-shot prompt

```text
Classify each review as Positive or Negative. Return one label per line.

Examples:
"I loved every minute." -> Positive
"It was boring." -> Negative
"I expected to dislike it, but enjoyed it." -> Positive
"Wonderful, another completely wasted evening." -> Negative

Now classify:
1. Not bad at all, actually.
2. Great, another two hours of my life I'll never get back.
```

Actual response, also displayed inside a Markdown code block:

```text
Positive
Negative
```

### Effectiveness and limitations

The intended labels are Positive for the first review and Negative for the
sarcastic second review. Both conditions classified both items correctly: 2/2
(100%) on this tiny test. Adding examples produced no observed accuracy gain,
although it demonstrated the intended output mapping. Both responses retained
Markdown code fences, so the examples did not eliminate that extra formatting.
Two items and one trial per condition are insufficient to establish that few-shot
prompting is generally useful or unnecessary. More varied reviews and repeated
trials would be needed to compare reliability.

### Connection to the homework

The few_shot_examples field provides SQL, Python, and orchestration examples.
Examples can clarify a format, but correctness must be checked by actual parsing
and execution. The handout's Orchestrator example omits inner quotes required by
its parser; copying an inconsistent example can encourage an invalid format.
This experiment did not modify those application configurations.

## Conclusion

In these observed comparisons, role-and-audience prompting made the explanation
more accessible, style prompting changed tone and presentation while retaining
the requested fact, and few-shot prompting produced no measurable accuracy gain
on the two review examples. These results describe the collected responses only.
They do not replace the separate live demonstration of database reading,
writing, orchestration order, and the four seeded role configurations.
