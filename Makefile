.PHONY: test build run clean
test:
	python -m unittest tests.test_keeper -v
	node --check bin/keeper.js
	bash -n bin/keeper.sh
	cd rust/mega-keeper-cli && cargo test --quiet
build:
	cd rust/mega-keeper-cli && cargo build --release
run:
	python3 keeper.py status
clean:
	rm -rf rust/mega-keeper-cli/target
