var parts = msg.payload.data.split(',');
var data = {};
data.module = msg.payload.module;
data.length = Number(parts[0]);
data.width = Number(parts[1]);
data.status = Number(parts[2]);
msg.payload = data;
return msg;

var data = {};
data.module = msg.payload.module;
data.data = String(msg.payload.length) + "," + String(msg.payload.width) + "," + String(msg.payload.status);
msg.payload = data;
return msg;

