# Frozen execution-time baseline v1

`execution_time_baseline_v1.json` records immutable historical observations.
The referenced prediction JSON files must not be overwritten. SHA-256 values
detect accidental changes. Missing experiment modes are recorded as `not_run`,
not synthesized after board disclosure.

Board values in this baseline are measured maxima for the stated fixed input
scenario. They are not automatically formal WCET values.
