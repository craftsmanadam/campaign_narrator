# Multi-Agentic Narrative Tabletop With Long Term Memory

## Yance Adam Martin

### **Introduction and Motivation:**

I am interested in the problem of long-term narrative capability in large language models (LLMs). While LLMs are clearly effective at generating content, they are known to struggle with coherence, consistency, and the lack of any native persistent memory. These limitations become more visible in systems that are expected to carry context forward over time.

This project will explore if those limitations can be addressed at a smaller, controlled scale. The goal is to keep the scope manageable within a 3–4 week timeframe while still producing something that demonstrates a repeatable pattern for improving long-term consistency keeping the work relevant to developers and researchers building stateful LLM systems.

A tabletop game environment provides a useful setting for this work. It combines long-running narrative, loosely defined but structured rules, and evolving state. This is complex enough to be meaningful, but still constrained enough to test memory, retrieval, and agent-based orchestration in a practical way.

### **Background and Related Work:**

The use of LLMs as a dungeon master (DM) has already been explored in prior research:

* [Exploring the Potential of LLM-based Agents as Dungeon Masters in Tabletop Role-playing Games](https://studenttheses.uu.nl/bitstream/handle/20.500.12932/47209/Thesis_Final.pdf) by Pavlos Sakellaridis  
* [CALYPSO: LLMs as Dungeon Masters’ Assistants](https://andrewhead.info/assets/pdf/calypso.pdf) by Andrew Zhu, Lara Martin, Andrew Head, and Chris Callison-Burch  
* [How LLMs are Shaping the Future of Virtual Reality](https://arxiv.org/html/2508.00737v1) by Süeda Özkaya, Santiago Berrezueta-Guzman, and Stefan Wagner

These works demonstrate the potential of LLMs as tools to assist or augment a human DM. However, based on this review, most approaches focus on single-agent or prompt-driven systems. To my knowledge, there has been limited exploration of an architected multi-agent system with persistent state.

There are also a number of existing tools and techniques that make this type of system feasible to prototype. These include Python-based dice rolling libraries such as [multi-dice](https://pypi.org/project/multi-dice/), [System Reference Documentation](https://www.dndbeyond.com/srd?srsltid=AfmBOoq3FwCJhRLhPymQC7t_RlsGOMNXzl0OwB03T1J9J7dnKNaCY03A) (SRD) for rules grounding, [Retrieval-Augmented Generation](https://arxiv.org/pdf/2005.11401) (RAG) for contextual recall, [ChromaDB](https://www.trychroma.com/), and Multi-Agentic architecture patterns.  This project is intended to bring these components together into a cohesive working solution.

### **Proposed Approach:**

In my approach, I want to break the problem down into a set of clear architectural components, each defined with a narrow scope to limit ambiguity and improve consistency:

* **Rule Corpus**: A curated subset of the SRD stored for runtime retrieval by the Rules Agent. This serves as the reference for rule grounding within the system. (Milestone: Week 1\)  
* **Rules Agent**: Responsible for determining which rules apply to a given player action, retrieving those rules, and producing an outcome for execution and validation. (Milestone: Week 1\)  
* **Campaign Agent**: Responsible for defining and maintaining the overall campaign structure. This includes major non-player characters, major factions, high-level narrative direction, and key story milestones. It is also responsible for validating that generated content remains in alignment with the defined campaign and appropriate adjustments. (Milestone: Week 1\)  
* **Module Agent**: Responsible for defining an individual module and its local narrative arc within the campaign. It creates supporting NPCs and scenes specific to the module and ensures that the local story does not violate the broader campaign arc. For the scope of this project, a module will be limited to a single session or interaction. (Milestone: Week 2\)  
* **Narrator Agent**: Responsible for generating the player-facing narration of the session. It translates the outputs of the Module Agent and Rules Agent, along with player interactions, into coherent narrative and dialogue. (Milestone: Week 2\)  
* **State Manager**: Responsible for maintaining persistent game state across interactions, including player HP, inventory, quest flags, discovered information, and NPC relationships. (Milestone: Week 2\)  
* **Orchestrator**: A background control component responsible for coordinating the flow between agents. It determines which component acts at each step and ensures consistency and avoids conflicting outputs between agents. (Milestone: Week 3\)

### **Data and Resources:**

For this project, I will leverage the previously mentioned SRD. I will curate this down to a subset, as a full implementation of the corpus is not feasible within the available time. In addition, I will define a limited set of local campaign data, such as NPCs and narrative elements to support the overall arc.

Because this is intended to function as a campaign framework, the system will also store data generated during sessions to maintain continuity across interactions. Finally, the primary API used will be OpenAI, which will support agent reasoning, narration, and decision-making.

### **Evaluation Plan:**

I will use a rubric-based evaluation to validate the success of the project against a single-agent LLM baseline using prompt-based interaction. The rubric will focus on four areas: 

1. **Narrative Consistency**: Measured by whether prior events, NPC behavior, and story elements remain coherent over time  
2. **Rules Application**: Measured by whether appropriate mechanics are selected and applied consistently  
3. **State Persistence**: Measured by whether player condition, inventory, and quest progression are accurately maintained across sessions.  
4. **Player Enjoymen**t: The ultimate measure- which interaction is the most enjoyable for the player in an interactive narrative bound by structured rules.

This binds the evaluation to a level that can be completed in the time constraint for the project. Results will be analyzed by comparing rubric scores across identical test scenarios between the baseline and multi-agent system. Success will be defined as outperforming the baseline in at least 3 of 4 rubric categories across test scenarios.

### **Feasibility and Scope:**

Time and cost are the primary risks for this project. I will limit the SRD corpus to reduce overhead, and data structures will be simplified to remain within scope. API limits and cost will be monitored closely, as multiple agents operating on large text inputs may increase API usage. This design prioritizes a functional prototype over a fully optimized implementation.

### **Ethics, Privacy, and Security:**

For this project, I am intentionally constraining the system to use only publicly available data, primarily the SRD and locally defined narrative content. Because of this, the project does not introduce any fundamentally new ethical concerns beyond those already present in existing LLM systems.

However, the use of persistent state and memory does have implications if applied to other domains. If this pattern were extended to systems that store user-generated or sensitive data, it would introduce issues of data privacy, retention, and misuse. In those cases, safeguards such as data minimization, anonymization, access controls, and clear boundaries on what is persisted would become necessary.

For the scope of this project, the use of synthetic and public data keeps these risks minimal, while still demonstrating the architectural patterns that could raise ethical concerns in more sensitive applications.

### **References:**

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). *Retrieval-augmented generation for knowledge-intensive NLP tasks*.

Özkaya, S., Berrezueta-Guzman, S., & Wagner, S. (Year). *How LLMs are shaping the future of virtual reality*.

Sakellaridis, P. (Year). *Exploring the potential of LLM-based agents as dungeon masters in tabletop role-playing games*. 

Zhu, A., Martin, L., Head, A., & Callison-Burch, C. (Year). *CALYPSO: LLMs as dungeon masters’ assistants*.

Wizards of the Coast. (2025). *System Reference Document (SRD) 5.2*. 