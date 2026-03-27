from dataclasses import dataclass


@dataclass
class TwStockAnalyticsAdapter:
    open: list[float]
    price: list[float]
    high: list[float]
    low: list[float]
    capacity: list[int]

    def moving_average(self, data: list[float], days: int) -> list[float]:
        result: list[float] = []
        working = data[:]
        for _ in range(len(working) - days + 1):
            result.append(round(sum(working[-days:]) / days, 2))
            working.pop()
        return result[::-1]

    def continuous(self, data: list[float]) -> int:
        diff = [1 if data[-i] > data[-i - 1] else -1 for i in range(1, len(data))]
        cont = 0
        for value in diff:
            if value == diff[0]:
                cont += 1
            else:
                break
        return cont * diff[0]

    def ma_bias_ratio(self, day1: int, day2: int) -> list[float]:
        data1 = self.moving_average(self.price, day1)
        data2 = self.moving_average(self.price, day2)
        result = [data1[-i] - data2[-i] for i in range(1, min(len(data1), len(data2)) + 1)]
        return result[::-1]

    def ma_bias_ratio_pivot(self, data: list[float], sample_size: int = 5, position: bool = False):
        sample = data[-sample_size:]
        if position:
            check_value = max(sample)
            pre_check_value = max(sample) > 0
        else:
            check_value = min(sample)
            pre_check_value = max(sample) < 0

        return (
            (
                sample_size - sample.index(check_value) < 4
                and sample.index(check_value) != sample_size - 1
                and pre_check_value
            ),
            sample_size - sample.index(check_value) - 1,
            check_value,
        )
