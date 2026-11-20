const express = require('express');
const mongoose = require('mongoose');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// --- MongoDB connection ---
const MONGO_URL = process.env.MONGO_URL || 'mongodb://localhost:27017/emidb';

mongoose.connect(MONGO_URL, { serverSelectionTimeoutMS: 3000 })
  .then(() => console.log('MongoDB connected'))
  .catch(err => console.error('MongoDB connection error:', err.message));

// --- Schema ---
const calcSchema = new mongoose.Schema({
  principal: Number,
  rate: Number,
  months: Number,
  emi: Number,
  servedBy: String,
  createdAt: { type: Date, default: Date.now }
});

const Calc = mongoose.model('calculations', calcSchema);

// --- EMI formula ---
function computeEMI(P, annualRate, n) {
  const r = annualRate / 12 / 100;
  if (r === 0) return P / n;                    // 0% interest edge case
  const emi = (P * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
  return Math.round(emi * 100) / 100;
}

// --- POST /api/emi ---
app.post('/api/emi', async (req, res) => {
  const { principal, rate, months } = req.body;

  // Server-side validation: all must be positive numbers
  if (!principal || !rate || !months ||
      principal <= 0 || rate <= 0 || months <= 0) {
    return res.status(400).json({ error: 'All fields must be positive numbers.' });
  }

  const P = parseFloat(principal);
  const r = parseFloat(rate);
  const n = parseInt(months);

  const emi = computeEMI(P, r, n);
  const totalPayment = Math.round(emi * n * 100) / 100;
  const totalInterest = Math.round((totalPayment - P) * 100) / 100;

  const podName = process.env.HOSTNAME || 'local';

  // Save to MongoDB
  try {
    await Calc.create({ principal: P, rate: r, months: n, emi, servedBy: podName });
  } catch (err) {
    console.error('DB save error:', err.message);
  }

  res.json({ emi, totalPayment, totalInterest, servedBy: podName });
});

// --- GET /api/history ---
app.get('/api/history', async (req, res) => {
  try {
    const history = await Calc.find().sort({ createdAt: -1 }).limit(10);
    res.json(history);
  } catch (err) {
    res.status(500).json({ error: 'DB error' });
  }
});

// --- GET /health ---
app.get('/health', async (req, res) => {
  // 200 only if mongoose is actually connected
  if (mongoose.connection.readyState === 1) {
    res.status(200).json({ status: 'ok' });
  } else {
    res.status(503).json({ status: 'unavailable' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Listening on port ${PORT}`));
