/**
 * ZMQ PUB/SUB event publisher — hands-side (INFRA-05, checker issue #07).
 *
 * Two-endpoint topology: each tier BINDS its own PUB endpoint and SUBSCRIBES
 * to the peer's PUB endpoint. No string-mangling — endpoints are verbatim from
 * BotConfig.infra.zmq_events_{brain,hands}_endpoint.
 */

import { Publisher, Subscriber } from "zeromq";

export class EventPublisher {
	private pub = new Publisher();
	private sub = new Subscriber();

	constructor(
		private brainEndpoint: string,
		private handsEndpoint: string,
		private tier: "brain" | "hands",
	) {}

	async connect(): Promise<void> {
		this.sub.subscribe("");
		if (this.tier === "brain") {
			await this.pub.bind(this.brainEndpoint);
			this.sub.connect(this.handsEndpoint);
		} else {
			await this.pub.bind(this.handsEndpoint);
			this.sub.connect(this.brainEndpoint);
		}
	}

	async publish(msg: object): Promise<void> {
		await this.pub.send(JSON.stringify(msg));
	}

	/** Async iterator over incoming events from the peer's PUB. */
	async *receive(): AsyncGenerator<object> {
		for await (const [buf] of this.sub) {
			yield JSON.parse(buf.toString());
		}
	}

	close(): void {
		this.pub.close();
		this.sub.close();
	}
}
