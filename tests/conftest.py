import torch


def pytest_sessionstart() -> None:
    # Tiny test tensors; this affects this test process only, not library users.
    torch.set_num_threads(1)
