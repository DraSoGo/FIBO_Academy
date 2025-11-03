var data = {}
data.module = String(msg.payload.module);
data.high = Number(Math.abs(Number(msg.payload.data)/10-30.5).toFixed(1));
msg.payload = data
return msg;