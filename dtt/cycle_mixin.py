from typing import List, Set


class CycleMixin:
    def detect_circular_dependencies(self) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        on_path: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str):
            visited.add(node)
            on_path.add(node)
            stack.append(node)
            tech = self.all_technologies.get(node)
            if tech:
                for nxt in tech.unlocked_tech_ids:
                    if nxt not in self.all_technologies:
                        continue
                    if nxt not in visited:
                        dfs(nxt)
                    elif nxt in on_path:
                        if nxt in stack:
                            idx = stack.index(nxt)
                            cycle = stack[idx:] + [nxt]
                            if cycle not in cycles:
                                cycles.append(cycle)
            stack.pop()
            on_path.remove(node)

        for tid in list(self.all_technologies.keys()):
            if tid not in visited:
                dfs(tid)
        return cycles

    def report_circular_dependencies(self) -> None:
        print(self._l("msg_detecting_cycles"))
        cycles = self.detect_circular_dependencies()
        if cycles:
            print(self._l("msg_cycles_found", count=len(cycles)))
            self_loops = []
            complex_cycles = []
            for cycle in cycles:
                if len(cycle) == 2 and cycle[0] == cycle[1]:
                    self_loops.append(cycle[0])
                else:
                    complex_cycles.append(cycle)
            if self_loops:
                print(self._l("msg_self_loops_header", count=len(self_loops)))
                for tech in self_loops:
                    # Localized self-loop entry
                    print(self._l("msg_self_loop_entry", tech=tech))
            if complex_cycles:
                print(self._l("msg_complex_loops_header", count=len(complex_cycles)))
                for i, cycle in enumerate(complex_cycles, 1):
                    cycle_str = " -> ".join(cycle)
                    print(self._l("msg_cycle_entry", index=i, cycle=cycle_str))
            print("")
        else:
            print(self._l("msg_no_cycles"))
