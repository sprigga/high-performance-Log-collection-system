"""
效能比較分析工具
用於比較優化系統和簡化系統的測試結果
"""
from typing import Dict, Any

class PerformanceComparison:
    """效能比較分析類別"""

    def __init__(self):
        self.optimized_results: Dict[str, Any] = {}
        self.simple_results: Dict[str, Any] = {}

    def set_optimized_results(self, **kwargs):
        """設定優化系統的測試結果"""
        self.optimized_results = kwargs

    def set_simple_results(self, **kwargs):
        """設定簡化系統的測試結果"""
        self.simple_results = kwargs

    def calculate_improvement(self, optimized: float, simple: float,
                            higher_is_better: bool = True) -> float:
        """
        計算改善百分比

        Args:
            optimized: 優化系統的數值
            simple: 簡化系統的數值
            higher_is_better: True 表示數值越高越好（如吞吐量）
                            False 表示數值越低越好（如回應時間）

        Returns:
            改善百分比（正數表示改善，負數表示退步）
        """
        if simple == 0:
            return 0

        if higher_is_better:
            # 吞吐量：越高越好
            return ((optimized - simple) / simple) * 100
        else:
            # 回應時間：越低越好
            return ((simple - optimized) / simple) * 100

    def print_comparison(self):
        """輸出比較結果"""
        print("=" * 80)
        print("  📊 效能比較分析報告")
        print("=" * 80)

        # 吞吐量比較
        print("\n⚡ 吞吐量 (logs/秒)")
        print("-" * 80)
        opt_throughput = self.optimized_results.get('throughput', 0)
        sim_throughput = self.simple_results.get('throughput', 0)
        improvement = self.calculate_improvement(opt_throughput, sim_throughput, True)

        print(f"  優化系統: {opt_throughput:>10.2f} logs/秒")
        print(f"  簡化系統: {sim_throughput:>10.2f} logs/秒")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # 回應時間比較
        print("\n⏱️  平均回應時間 (ms)")
        print("-" * 80)
        opt_avg = self.optimized_results.get('avg_response_time', 0)
        sim_avg = self.simple_results.get('avg_response_time', 0)
        improvement = self.calculate_improvement(opt_avg, sim_avg, False)

        print(f"  優化系統: {opt_avg:>10.2f} ms")
        print(f"  簡化系統: {sim_avg:>10.2f} ms")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # P95 回應時間比較
        print("\n📉 P95 回應時間 (ms)")
        print("-" * 80)
        opt_p95 = self.optimized_results.get('p95_response_time', 0)
        sim_p95 = self.simple_results.get('p95_response_time', 0)
        improvement = self.calculate_improvement(opt_p95, sim_p95, False)

        print(f"  優化系統: {opt_p95:>10.2f} ms")
        print(f"  簡化系統: {sim_p95:>10.2f} ms")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # P99 回應時間比較
        print("\n📉 P99 回應時間 (ms)")
        print("-" * 80)
        opt_p99 = self.optimized_results.get('p99_response_time', 0)
        sim_p99 = self.simple_results.get('p99_response_time', 0)
        improvement = self.calculate_improvement(opt_p99, sim_p99, False)

        print(f"  優化系統: {opt_p99:>10.2f} ms")
        print(f"  簡化系統: {sim_p99:>10.2f} ms")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # 失敗率比較
        print("\n❌ 失敗率 (%)")
        print("-" * 80)
        opt_fail = self.optimized_results.get('failure_rate', 0)
        sim_fail = self.simple_results.get('failure_rate', 0)
        improvement = self.calculate_improvement(opt_fail, sim_fail, False)

        print(f"  優化系統: {opt_fail:>10.2f}%")
        print(f"  簡化系統: {sim_fail:>10.2f}%")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # 總耗時比較
        print("\n⏲️  總耗時 (秒)")
        print("-" * 80)
        opt_time = self.optimized_results.get('total_time', 0)
        sim_time = self.simple_results.get('total_time', 0)
        improvement = self.calculate_improvement(opt_time, sim_time, False)

        print(f"  優化系統: {opt_time:>10.2f} 秒")
        print(f"  簡化系統: {sim_time:>10.2f} 秒")
        print(f"  改善幅度: {improvement:>10.2f}% {'✅' if improvement > 0 else '❌'}")

        # 綜合評分
        print("\n" + "=" * 80)
        print("  🏆 綜合評分")
        print("=" * 80)

        # 計算加權總分（各項指標權重）
        weights = {
            'throughput': 0.30,      # 吞吐量 30%
            'p95': 0.25,             # P95 25%
            'avg_response': 0.20,    # 平均回應 20%
            'failure_rate': 0.15,    # 失敗率 15%
            'total_time': 0.10       # 總耗時 10%
        }

        throughput_imp = self.calculate_improvement(opt_throughput, sim_throughput, True)
        p95_imp = self.calculate_improvement(opt_p95, sim_p95, False)
        avg_imp = self.calculate_improvement(opt_avg, sim_avg, False)
        fail_imp = self.calculate_improvement(opt_fail, sim_fail, False)
        time_imp = self.calculate_improvement(opt_time, sim_time, False)

        total_improvement = (
            throughput_imp * weights['throughput'] +
            p95_imp * weights['p95'] +
            avg_imp * weights['avg_response'] +
            fail_imp * weights['failure_rate'] +
            time_imp * weights['total_time']
        )

        print(f"\n  總體改善: {total_improvement:>10.2f}%")

        if total_improvement > 50:
            print("  評級: ⭐⭐⭐⭐⭐ 優秀")
        elif total_improvement > 30:
            print("  評級: ⭐⭐⭐⭐ 良好")
        elif total_improvement > 10:
            print("  評級: ⭐⭐⭐ 普通")
        elif total_improvement > 0:
            print("  評級: ⭐⭐ 有改善")
        else:
            print("  評級: ⭐ 需要改進")

        print("\n" + "=" * 80)


# ==========================================
# 使用範例
# ==========================================
if __name__ == "__main__":
    # 創建比較器
    comparison = PerformanceComparison()

    # 設定優化系統結果（範例數據）
    comparison.set_optimized_results(
        throughput=12500.00,
        avg_response_time=45.50,
        p95_response_time=85.00,
        p99_response_time=120.00,
        failure_rate=0.0,
        total_time=0.80
    )

    # 設定簡化系統結果（範例數據）
    comparison.set_simple_results(
        throughput=3500.00,
        avg_response_time=180.00,
        p95_response_time=450.00,
        p99_response_time=680.00,
        failure_rate=2.5,
        total_time=2.86
    )

    # 輸出比較結果
    comparison.print_comparison()

    # 說明
    print("\n💡 說明：")
    print("  • 正數改善百分比表示優化系統表現更好")
    print("  • 此為範例數據，請替換為實際測試結果")
    print("  • 建議執行多次測試取平均值以獲得更準確的結果")
