.PHONY: test build run clean
test:
	python -m compileall -q keeper.py
	python -m unittest tests.test_keeper -v
	node --check bin/keeper.js
	bash -n bin/keeper.sh
	cd rust/m-keeper-cli && cargo test --quiet
build:
	cd rust/m-keeper-cli && cargo build --release
run:
	python3 keeper.py status
clean:
	rm -rf rust/m-keeper-cli/target
