import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Linking,
} from "react-native";
import * as WebBrowser from "expo-web-browser";
import { splitwiseApi, gmailApi, telegramApi } from "../services/api";

const TELEGRAM_BOT_USERNAME = "YourBotUsername";

interface StepProps {
  done: boolean;
  loading: boolean;
  onConnect: () => void;
  title: string;
  description: string;
  buttonLabel: string;
}

function StepCard({ done, loading, onConnect, title, description, buttonLabel }: StepProps) {
  return (
    <View style={styles.stepCard}>
      <Text style={styles.stepTitle}>{done ? `✅ ${title}` : title}</Text>
      <Text style={styles.stepDesc}>{description}</Text>
      {!done && (
        <TouchableOpacity style={styles.connectBtn} onPress={onConnect} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.connectBtnText}>{buttonLabel}</Text>
          )}
        </TouchableOpacity>
      )}
    </View>
  );
}

interface Props {
  onComplete: () => void;
}

export default function OnboardingScreen({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [splitwiseDone, setSplitwise] = useState(false);
  const [gmailDone, setGmail] = useState(false);
  const [telegramDone, setTelegram] = useState(false);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPoll(), []);

  const connectSplitwise = async () => {
    setLoading(true);
    try {
      const { data } = await splitwiseApi.getConnectUrl();
      await WebBrowser.openBrowserAsync(data.oauth_url);
      pollRef.current = setInterval(async () => {
        const { data: status } = await splitwiseApi.getStatus();
        if (status.connected) {
          stopPoll();
          setSplitwise(true);
          setStep(1);
          setLoading(false);
        }
      }, 2000);
    } catch {
      setLoading(false);
    }
  };

  const connectGmail = async () => {
    setLoading(true);
    try {
      const { data } = await gmailApi.getConnectUrl();
      await WebBrowser.openBrowserAsync(data.oauth_url);
      pollRef.current = setInterval(async () => {
        const { data: status } = await gmailApi.getStatus();
        if (status.connected) {
          stopPoll();
          setGmail(true);
          setStep(2);
          setLoading(false);
        }
      }, 2000);
    } catch {
      setLoading(false);
    }
  };

  const openTelegram = async () => {
    await Linking.openURL(`tg://resolve?domain=${TELEGRAM_BOT_USERNAME}`);
    pollRef.current = setInterval(async () => {
      const { data: status } = await telegramApi.getStatus();
      if (status.linked) {
        stopPoll();
        setTelegram(true);
        setTimeout(onComplete, 1000);
      }
    }, 3000);
  };

  const progress = [splitwiseDone, gmailDone, telegramDone].filter(Boolean).length;

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Setup SplitEase</Text>

      <View style={styles.progressRow}>
        {[0, 1, 2].map((i) => (
          <View
            key={i}
            style={[styles.dot, i < progress && styles.dotActive]}
          />
        ))}
      </View>

      <StepCard
        done={splitwiseDone}
        loading={loading && step === 0}
        onConnect={connectSplitwise}
        title="1. Connect Splitwise"
        description="Link your Splitwise account to add expenses automatically."
        buttonLabel="Connect Splitwise"
      />

      {step >= 1 && (
        <StepCard
          done={gmailDone}
          loading={loading && step === 1}
          onConnect={connectGmail}
          title="2. Connect Gmail"
          description="Allow SplitEase to monitor bank transaction emails."
          buttonLabel="Connect Gmail"
        />
      )}

      {step >= 2 && (
        <StepCard
          done={telegramDone}
          loading={false}
          onConnect={openTelegram}
          title="3. Link Telegram"
          description={`Open Telegram and send /start to @${TELEGRAM_BOT_USERNAME} to receive transaction alerts.`}
          buttonLabel={`Open @${TELEGRAM_BOT_USERNAME}`}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20, paddingTop: 60 },
  heading: { fontSize: 28, fontWeight: "bold", marginBottom: 16 },
  progressRow: { flexDirection: "row", gap: 8, marginBottom: 24 },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: "#ddd" },
  dotActive: { backgroundColor: "#6C63FF" },
  stepCard: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  stepTitle: { fontSize: 18, fontWeight: "600", marginBottom: 8 },
  stepDesc: { color: "#666", marginBottom: 16, lineHeight: 22 },
  connectBtn: {
    backgroundColor: "#6C63FF",
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
  },
  connectBtnText: { color: "#fff", fontWeight: "600", fontSize: 16 },
});
