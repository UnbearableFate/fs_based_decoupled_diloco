from pathlib import Path


def test_p07_d8_deadline_override_fits_inside_pbs_walltime():
    root = Path(__file__).resolve().parents[2]
    host = (root / "scripts/miyabi/run_p06c_d8_r2_host.sh").read_text()
    p07 = (root / "scripts/miyabi/run_duraloco_p07_d8_r2.pbs").read_text()

    assert 'D8_DEADLINE_SECONDS="${D8_DEADLINE_SECONDS:-840}"' in host
    assert "deadline=$((SECONDS + D8_DEADLINE_SECONDS))" in host
    assert "D8_DEADLINE_SECONDS=1800" in p07
    assert "#PBS -l walltime=00:35:00" in p07

