# S32K148 iso14229 real automotive blind WCET suite

Validation-only tasks derived from driftregion/iso14229 at commit
`b0e92b14fcc384d42bfd01ecd7f745addb6bf761` (MIT). Task IDs:

- 0: multi-DID response packing (unsupported before board);
- 1: address/length decode, 14.848848 us / 17.076175 us safe;
- 2: TransferData block copy, 14.707500 us / 16.913625 us safe;
- 3: SecurityAccess key validation, 20.101308 us / 23.116504 us safe.

Read `g_star_iso14229_real_complete`, `g_star_iso14229_real_current`,
`g_star_iso14229_real_results.point_count`, `.sample_count`,
`.measurement_overhead_cycles`, `.error_flags`, and `.points`.

Success requires complete=1, current=3, point_count=4, sample_count=40, and
error_flags=0. ELF SHA-256:
`C0CCEFF9E1B6AADED6CBFE396FFBAB8633708CDFD9D41757C89CF7AD0050299A`
