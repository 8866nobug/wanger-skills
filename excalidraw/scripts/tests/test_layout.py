import unittest

from excalidraw import layout, models


class TestLayout(unittest.TestCase):
    def _chain(self, n=4):
        nodes = [models.Node("process", f"n{i}", sem_id=f"n{i}") for i in range(n)]
        edges = [models.Edge(f"n{i}", f"n{i + 1}") for i in range(n - 1)]
        return nodes, edges

    def test_flow_chain_depths(self):
        nodes, edges = self._chain(4)
        pos = layout.flow(nodes, edges)
        # 链式结构应得到严格递增的行（深度），且无重复行
        depths = [p[1] for p in pos]
        self.assertEqual(len(set(depths)), 4)
        self.assertEqual(sorted(depths), depths)

    def test_flow_branch_no_overlap(self):
        nodes = [
            models.Node("terminator", "开始", sem_id="start"),
            models.Node("decision", "判断", sem_id="d1"),
            models.Node("process", "左", sem_id="left"),
            models.Node("process", "右", sem_id="right"),
            models.Node("terminator", "结束", sem_id="end"),
        ]
        edges = [
            models.Edge("start", "d1"),
            models.Edge("d1", "left"),
            models.Edge("d1", "right"),
            models.Edge("left", "end"),
            models.Edge("right", "end"),
        ]
        pos = layout.flow(nodes, edges)
        # 同一行（同 y）的节点 x 区间不得重叠
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if pos[i][1] == pos[j][1]:
                    wi, hi = layout.node_size(nodes[i].kind)
                    wj, hj = layout.node_size(nodes[j].kind)
                    overlap = (pos[i][0] < pos[j][0] + wj and
                               pos[j][0] < pos[i][0] + wi)
                    self.assertFalse(overlap, f"节点 {i} 与 {j} 重叠")

    def test_flow_cycle_no_crash(self):
        nodes = [models.Node("process", "a", sem_id="a"),
                 models.Node("process", "b", sem_id="b")]
        edges = [models.Edge("a", "b"), models.Edge("b", "a")]
        pos = layout.flow(nodes, edges)
        self.assertEqual(len(pos), 2)

    def test_crossings_metric(self):
        nodes = [models.Node("process", "a", sem_id="a"),
                 models.Node("process", "b", sem_id="b")]
        edges = [models.Edge("a", "b")]
        # 单边无交叉
        self.assertEqual(layout.count_crossings(nodes, edges, [(0, 0), (0, 100)]), 0)

    def test_flow_removes_simple_crossing(self):
        # 输入顺序为 [A,B] / [C,D]，边 A->D、B->C；最优布局应消除交叉
        nodes = [
            models.Node("process", "A", sem_id="A"),
            models.Node("process", "B", sem_id="B"),
            models.Node("process", "C", sem_id="C"),
            models.Node("process", "D", sem_id="D"),
        ]
        edges = [models.Edge("A", "D"), models.Edge("B", "C")]
        pos = layout.flow(nodes, edges)
        self.assertEqual(layout.count_crossings(nodes, edges, pos), 0)

    def test_bounds(self):
        nodes = [models.Node("process", "x", sem_id="a"),
                 models.Node("process", "y", sem_id="b")]
        pos = [(0.0, 0.0), (100.0, 200.0)]
        mnx, mny, mxx, mxy = layout.bounds(pos, nodes)
        w, h = layout.node_size("process")
        self.assertEqual((mnx, mny), (0.0, 0.0))
        self.assertEqual((mxx, mxy), (100.0 + w, 200.0 + h))


if __name__ == "__main__":
    unittest.main()
