class CameraTalkProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.frame = new ArrayBuffer(640);
    this.view = new DataView(this.frame);
    this.position = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (const sample of channel) {
      this.sum += sample;
      this.count++;
      this.phase += 8000;
      if (this.phase < sampleRate) continue;
      this.phase -= sampleRate;
      const mean = Math.max(-1, Math.min(1, this.sum / this.count));
      this.view.setInt16(this.position * 2, Math.round(mean * 32767), true);
      this.sum = 0;
      this.count = 0;
      this.position++;
      if (this.position === 320) {
        this.port.postMessage(this.frame, [this.frame]);
        this.frame = new ArrayBuffer(640);
        this.view = new DataView(this.frame);
        this.position = 0;
      }
    }
    return true;
  }
}

registerProcessor("camera-talk", CameraTalkProcessor);
