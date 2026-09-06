# Failure Lab

This directory is an incident-style regression register, not a claim that every production failure has been observed. Each case records `failure → impact → expected fail-closed response → regression test`.

The checked-in cases cover SEC unavailability, LLM timeout, malformed documents, conflicting restatements, model-population mismatch and component-version drift. Database and object-storage chaos testing require external infrastructure and remain **NOT RUN**.
