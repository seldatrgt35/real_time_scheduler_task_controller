"""Tkinter desktop interface for STAR file-based analysis."""

from __future__ import annotations

import tempfile
from pathlib import Path
from tkinter import Tk, filedialog, messagebox
from tkinter import StringVar, Text
from tkinter import ttk

from task_admission_framework.admission.admission_controller import AdmissionController
from task_admission_framework.calibration.execution_admission import (
    evaluate_execution_admission,
)
from task_admission_framework.calibration.workload_cost_loader import (
    WorkloadCostLoader,
)
from task_admission_framework.pipeline.exceptions import PipelineError
from task_admission_framework.rules.exceptions import RuleError
from task_admission_framework.rules.rule_database import RuleDatabase
from task_admission_framework.rules.rule_loader import RuleLoader


class StarGui:
    """Small UI where the user selects source, hardware, and entry method."""

    _DEFAULT_STACK_SIZE = 512
    _DEFAULT_CRITICALITY = "HIGH"

    def __init__(self) -> None:
        self._root = Tk()
        self._root.title("STAR Task Admission")
        self._root.geometry("980x720")
        self._root.minsize(860, 620)

        base_path = Path(__file__).parent
        self._source_path = StringVar(
            value=str(base_path / "examples" / "sensor_task.c")
        )
        self._entry_function = StringVar(value="SensorTask")
        self._hardware_name = StringVar(value="S32K148")
        self._period_ms = StringVar(value="10")
        self._priority = StringVar(value="3")
        self._status = StringVar(value="Ready")
        self._task_rows: list[dict[str, str]] = []

        self._output: Text
        self._task_table: ttk.Treeview
        self._build_layout()

    def run(self) -> None:
        """Start the Tkinter event loop."""

        self._root.mainloop()

    def _build_layout(self) -> None:
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(2, weight=1)

        input_frame = ttk.LabelFrame(self._root, text="Analyze Task", padding=12)
        input_frame.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        self._add_file_row(
            input_frame,
            row=0,
            label="C / C++ Source",
            variable=self._source_path,
            filetypes=(
                ("C/C++ files", "*.c *.cpp *.cc *.cxx"),
                ("All files", "*.*"),
            ),
        )

        ttk.Label(input_frame, text="Method / Function").grid(
            row=1,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Entry(input_frame, textvariable=self._entry_function).grid(
            row=1,
            column=1,
            columnspan=2,
            padx=8,
            pady=4,
            sticky="ew",
        )

        ttk.Label(input_frame, text="Hardware").grid(
            row=2,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Combobox(
            input_frame,
            textvariable=self._hardware_name,
            values=("S32K148",),
            state="readonly",
        ).grid(row=2, column=1, columnspan=2, padx=8, pady=4, sticky="ew")

        ttk.Label(input_frame, text="Period").grid(
            row=3,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Combobox(
            input_frame,
            textvariable=self._period_ms,
            values=("5", "10", "20", "50", "100", "250", "500", "1000"),
            state="readonly",
        ).grid(row=3, column=1, columnspan=2, padx=8, pady=4, sticky="ew")

        ttk.Label(input_frame, text="Priority").grid(
            row=4,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Combobox(
            input_frame,
            textvariable=self._priority,
            values=("1", "2", "3"),
            state="readonly",
        ).grid(row=4, column=1, columnspan=2, padx=8, pady=4, sticky="ew")

        actions = ttk.Frame(input_frame)
        actions.grid(row=5, column=0, columnspan=3, pady=(12, 0), sticky="ew")
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Analyze Current Only", command=self._analyze).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(actions, text="Add Task", command=self._add_task).grid(
            row=0,
            column=1,
            padx=(8, 0),
            sticky="w",
        )
        ttk.Button(actions, text="Analyze All Tasks", command=self._analyze_taskset).grid(
            row=0,
            column=2,
            padx=(8, 0),
            sticky="w",
        )
        ttk.Label(actions, textvariable=self._status).grid(
            row=0,
            column=3,
            padx=(12, 0),
            sticky="w",
        )

        taskset_frame = ttk.LabelFrame(self._root, text="Task Set", padding=12)
        taskset_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        taskset_frame.columnconfigure(0, weight=1)
        columns = ("task", "function", "period", "priority", "hardware", "source")
        self._task_table = ttk.Treeview(
            taskset_frame,
            columns=columns,
            show="headings",
            height=5,
        )
        for column, heading, width in (
            ("task", "Task", 160),
            ("function", "Function", 180),
            ("period", "Period", 80),
            ("priority", "Priority", 80),
            ("hardware", "Hardware", 100),
            ("source", "Source", 420),
        ):
            self._task_table.heading(column, text=heading)
            self._task_table.column(column, width=width, anchor="w")
        self._task_table.grid(row=0, column=0, sticky="ew")
        self._task_table.bind("<<TreeviewSelect>>", self._load_selected_task)
        ttk.Button(taskset_frame, text="Remove Selected", command=self._remove_task).grid(
            row=1,
            column=0,
            pady=(8, 0),
            sticky="w",
        )

        output_frame = ttk.LabelFrame(self._root, text="Result", padding=12)
        output_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._output = Text(output_frame, wrap="word", height=24)
        self._output.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            output_frame,
            orient="vertical",
            command=self._output.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._output.configure(yscrollcommand=scrollbar.set)

    def _add_file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: StringVar,
        filetypes: tuple[tuple[str, str], ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            padx=8,
            pady=4,
            sticky="ew",
        )
        ttk.Button(
            parent,
            text="Browse",
            command=lambda: self._browse(variable, filetypes),
        ).grid(row=row, column=2, sticky="e", pady=4)

    def _browse(
        self,
        variable: StringVar,
        filetypes: tuple[tuple[str, str], ...],
    ) -> None:
        selected = filedialog.askopenfilename(filetypes=filetypes)
        if selected:
            variable.set(selected)

    def _analyze(self) -> None:
        source_path = Path(self._source_path.get())
        entry_function = self._entry_function.get().strip()
        hardware_name = self._hardware_name.get().strip()
        period_ms = int(self._period_ms.get())
        priority = int(self._priority.get())

        if not source_path.exists():
            self._show_error(f"File not found: {source_path}")
            return

        if source_path.suffix.lower() not in {".c", ".cpp", ".cc", ".cxx"}:
            self._show_error("Please select a C or C++ source file.")
            return

        if not entry_function:
            self._show_error("Please enter a method or function name.")
            return

        hardware_path = self._hardware_path_for(hardware_name)
        rules_path = self._rules_path_for(hardware_name)
        if not hardware_path.exists() or not rules_path.exists():
            self._show_error(f"Unsupported hardware profile: {hardware_name}")
            return

        self._status.set("Analyzing...")
        self._root.update_idletasks()

        try:
            from task_admission_framework.pipeline.analysis_pipeline import (
                AnalysisPipeline,
            )

            with tempfile.TemporaryDirectory(prefix="star_gui_") as temp_dir:
                descriptor_path = self._write_descriptor(
                    Path(temp_dir),
                    entry_function,
                    period_ms,
                    priority,
                )
                session = AnalysisPipeline().analyze(
                    source_file=source_path,
                    descriptor_file=descriptor_path,
                    hardware_profile_file=hardware_path,
                )
            rules = RuleLoader().load(rules_path)
            rule_database = RuleDatabase(rules)
            decision = AdmissionController().evaluate(session, rule_database)
            workload_profile = WorkloadCostLoader().load(
                Path(__file__).parent
                / "calibration"
                / "profiles"
                / "S32K148_workload_costs.json"
            )
            execution = evaluate_execution_admission(
                session.task_profile,
                period_ms,
                workload_profile,
            )
        except PipelineError as exc:
            self._status.set("Analysis failed")
            self._set_output(f"STAR analysis failed: {exc}")
            return
        except RuleError as exc:
            self._status.set("Rule lookup failed")
            self._set_output(f"STAR rule database failed: {exc}")
            return
        except Exception as exc:
            self._status.set("Failed")
            self._set_output(f"STAR failed: {exc}")
            return

        self._status.set(f"Execution admission: {execution.status}")
        self._set_output(self._format_result(session, decision, execution))

    def _add_task(self) -> None:
        source_path = Path(self._source_path.get())
        entry_function = self._entry_function.get().strip()
        hardware_name = self._hardware_name.get().strip()
        period_ms = self._period_ms.get()
        priority = self._priority.get()

        if not source_path.exists():
            self._show_error(f"File not found: {source_path}")
            return

        if source_path.suffix.lower() not in {".c", ".cpp", ".cc", ".cxx"}:
            self._show_error("Please select a C or C++ source file.")
            return

        if not entry_function:
            self._show_error("Please enter a method or function name.")
            return

        row = {
            "task": entry_function,
            "function": entry_function,
            "period": period_ms,
            "priority": priority,
            "hardware": hardware_name,
            "source": str(source_path),
        }
        self._task_rows.append(row)
        self._task_table.insert(
            "",
            "end",
            values=(
                row["task"],
                row["function"],
                f"{row['period']} ms",
                row["priority"],
                row["hardware"],
                row["source"],
            ),
        )
        self._status.set(f"Task added: {entry_function}")

    def _remove_task(self) -> None:
        selected_items = self._task_table.selection()
        if not selected_items:
            return

        for item in reversed(selected_items):
            index = self._task_table.index(item)
            self._task_table.delete(item)
            if 0 <= index < len(self._task_rows):
                self._task_rows.pop(index)

        self._status.set("Selected task removed")

    def _load_selected_task(self, _event=None) -> None:
        selected_items = self._task_table.selection()
        if not selected_items:
            return

        index = self._task_table.index(selected_items[0])
        if not 0 <= index < len(self._task_rows):
            return

        row = self._task_rows[index]
        self._source_path.set(row["source"])
        self._entry_function.set(row["function"])
        self._hardware_name.set(row["hardware"])
        self._period_ms.set(row["period"])
        self._priority.set(row["priority"])

    def _analyze_taskset(self) -> None:
        if not self._task_rows:
            self._show_error("Add at least one task to the task set.")
            return

        self._status.set("Analyzing task set...")
        self._root.update_idletasks()

        try:
            from task_admission_framework.taskset.taskset_analyzer import (
                TaskSetAnalyzer,
            )
            from task_admission_framework.taskset.taskset_entry import TaskSetEntry

            entries = [
                TaskSetEntry(
                    name=row["task"],
                    source_file=Path(row["source"]),
                    entry_function=row["function"],
                    period_ms=int(row["period"]),
                    deadline_ms=int(row["period"]),
                    priority=int(row["priority"]),
                    hardware_profile_file=self._hardware_path_for(row["hardware"]),
                    rules_file=self._rules_path_for(row["hardware"]),
                )
                for row in self._task_rows
            ]
            result = TaskSetAnalyzer().analyze(entries)
        except PipelineError as exc:
            self._status.set("Task set analysis failed")
            self._set_output(f"STAR task-set analysis failed: {exc}")
            return
        except RuleError as exc:
            self._status.set("Rule lookup failed")
            self._set_output(f"STAR rule database failed: {exc}")
            return
        except Exception as exc:
            self._status.set("Failed")
            self._set_output(f"STAR task-set failed: {exc}")
            return

        self._status.set(f"System: {result.system_status}")
        self._set_output(self._format_taskset_result(result))

    def _write_descriptor(
        self,
        temp_dir: Path,
        entry_function: str,
        period_ms: int,
        priority: int,
    ) -> Path:
        descriptor_path = temp_dir / "star_gui_task.yaml"
        descriptor_path.write_text(
            "\n".join(
                [
                    f"task_name: {entry_function}",
                    f"entry_function: {entry_function}",
                    f"period_ms: {period_ms}",
                    f"deadline_ms: {period_ms}",
                    f"priority: {priority}",
                    f"stack_size: {self._DEFAULT_STACK_SIZE}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return descriptor_path

    def _hardware_path_for(self, hardware_name: str) -> Path:
        return Path(__file__).parent / "hardware" / "profiles" / f"{hardware_name}.json"

    def _rules_path_for(self, hardware_name: str) -> Path:
        return (
            Path(__file__).parent
            / "rules"
            / "profiles"
            / f"{hardware_name}_rules.json"
        )

    @staticmethod
    def _format_result(session, decision, execution) -> str:
        descriptor = session.task_descriptor
        hardware = session.hardware_profile
        final_decision = {
            "PASS": "ACCEPTED",
            "FAIL": "REJECTED",
        }.get(execution.status, "UNVERIFIED")
        lines = [
            "STAR Task Result",
            "",
            f"Task: {descriptor.task_name}",
            f"Entry Function: {descriptor.entry_function}",
            f"Hardware: {hardware.name}",
            f"Period: {descriptor.period_ms} ms",
            f"Deadline: {descriptor.deadline_ms} ms",
            "",
            "Measured Complexity Model:",
            *[
                (
                    f"  {name}: {count} x "
                    f"{execution.cycle_breakdown[name] / count:.0f} cycles/unit "
                    f"= {execution.cycle_breakdown[name]:.0f} cycles"
                )
                for name, count in sorted(execution.workload_counts.items())
                if name in execution.cycle_breakdown
            ],
            "",
            (
                f"Calculated Complexity: {execution.estimated_cycles:.0f} cycles"
                if execution.estimated_cycles is not None
                else "Calculated Complexity: UNVERIFIED"
            ),
            f"Period Limit: {execution.safety_budget_cycles:.0f} cycles "
            f"({execution.safety_budget_us:.1f} us)",
            (
                f"Estimated Time: {execution.estimated_execution_us:.1f} us"
                if execution.estimated_execution_us is not None
                else "Estimated Time: UNVERIFIED"
            ),
            (
                f"Limit Usage: {execution.safety_budget_used:.2%}"
                if execution.safety_budget_used is not None
                else "Limit Usage: UNVERIFIED"
            ),
            "",
            f"FINAL DECISION: {final_decision}",
        ]
        if execution.status == "UNVERIFIED":
            lines.append("Reason:")
            lines.extend(f"  {note}" for note in execution.notes)
        return "\n".join(lines)

    @staticmethod
    def _format_taskset_result(result) -> str:
        lines = [
            "STAR TASK SET RESULT",
            "",
            f"FINAL SYSTEM DECISION: "
            f"{'ACCEPTED' if result.system_status == 'FEASIBLE' else result.system_status}",
            f"Tasks Analyzed: {len(result.task_results)}",
            "",
        ]
        for index, task in enumerate(result.task_results, start=1):
            final_decision = (
                "ACCEPTED"
                if task.execution_safety_status == "PASS"
                and task.scheduler_status == "FEASIBLE"
                else (
                    "UNVERIFIED"
                    if "UNVERIFIED"
                    in {task.execution_safety_status, task.scheduler_status}
                    else "REJECTED"
                )
            )
            lines.extend(
                [
                    f"{index}. {task.task_name}",
                    f"   Period / Deadline : {task.period_ms} / "
                    f"{task.deadline_ms} ms",
                    f"   Priority          : {task.priority}",
                ]
            )
            if task.workload_breakdown:
                breakdown = ", ".join(
                    f"{name}={count}"
                    for name, count in sorted(task.workload_breakdown.items())
                )
                lines.append(f"   Workload          : {breakdown}")
            if task.estimated_execution_time_us is not None:
                lines.extend(
                    [
                        f"   Complexity        : "
                        f"{task.estimated_execution_cycles:.0f} / "
                        f"{task.safety_budget_cycles:.0f} cycles",
                        f"   Estimated Time    : "
                        f"{task.estimated_execution_time_us:.1f} us",
                        f"   Limit Usage       : {task.safety_budget_used:.2%}",
                    ]
                )
            elif task.dynamic_bound_notes:
                lines.append("   Complexity        : UNVERIFIED")
                lines.extend(f"     {note}" for note in task.dynamic_bound_notes)
            lines.append(
                f"   Response Time     : "
                f"{task.response_time_us:.1f} / {task.deadline_ms * 1000:.1f} us"
                if task.response_time_us is not None
                else "   Response Time     : UNVERIFIED"
            )
            lines.extend([f"   DECISION          : {final_decision}", ""])
        return "\n".join(lines)

    def _set_output(self, text: str) -> None:
        self._output.delete("1.0", "end")
        self._output.insert("1.0", text)

    def _show_error(self, message: str) -> None:
        self._status.set("Input error")
        self._set_output(f"STAR GUI error:\n{message}")
        messagebox.showerror("STAR", message)


def run_gui() -> None:
    """Launch the STAR desktop interface."""

    StarGui().run()


if __name__ == "__main__":
    run_gui()
