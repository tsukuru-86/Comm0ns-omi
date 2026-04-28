import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/sockets/composite_transcription_socket.dart';
import 'package:omi/services/sockets/pure_socket.dart';

void main() {
  group('CompositeTranscriptionSocket hybrid fallback', () {
    test('connects and emits local transcripts when cloud socket is unavailable', () async {
      final primary = _FakeSocket(connectResult: true);
      final secondary = _FakeSocket(connectResult: false);
      final listener = _RecordingListener();
      final socket = CompositeTranscriptionSocket(primarySocket: primary, secondarySocket: secondary)
        ..setListener(listener);

      final connected = await socket.connect();

      expect(connected, isTrue);
      expect(socket.status, PureSocketStatus.connected);
      expect(listener.connectedCount, 1);

      primary.emit('[{"text":"hello","speaker_id":0}]');

      expect(listener.messages, ['[{"text":"hello","speaker_id":0}]']);
      expect(secondary.sentMessages, isEmpty);
    });

    test('uses cloud enrichment when both sockets are connected', () async {
      final primary = _FakeSocket(connectResult: true);
      final secondary = _FakeSocket(connectResult: true);
      final listener = _RecordingListener();
      final socket = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        sttProvider: 'on_device_whisper',
      )..setListener(listener);

      final connected = await socket.connect();
      expect(connected, isTrue);

      primary.emit('[{"text":"hello","speaker_id":0}]');

      expect(listener.messages, isEmpty);
      expect(secondary.sentMessages, hasLength(1));
      final suggested = jsonDecode(secondary.sentMessages.single) as Map<String, dynamic>;
      expect(suggested['type'], 'suggested_transcript');
      expect(suggested['stt_provider'], 'on_device_whisper');
      expect(suggested['segments'], isA<List>());

      secondary.emit('[{"text":"hello","speaker_id":1,"person_id":"person-1"}]');
      expect(listener.messages, ['[{"text":"hello","speaker_id":1,"person_id":"person-1"}]']);
    });

    test('continues locally if cloud socket closes after connection', () async {
      final primary = _FakeSocket(connectResult: true);
      final secondary = _FakeSocket(connectResult: true);
      final listener = _RecordingListener();
      final socket = CompositeTranscriptionSocket(primarySocket: primary, secondarySocket: secondary)
        ..setListener(listener);

      expect(await socket.connect(), isTrue);

      secondary.close(1006);
      primary.emit('[{"text":"offline","speaker_id":0}]');

      expect(socket.status, PureSocketStatus.connected);
      expect(listener.closedCodes, isEmpty);
      expect(listener.messages, ['[{"text":"offline","speaker_id":0}]']);
    });

    test('fails when primary local STT cannot connect', () async {
      final primary = _FakeSocket(connectResult: false);
      final secondary = _FakeSocket(connectResult: true);
      final listener = _RecordingListener();
      final socket = CompositeTranscriptionSocket(primarySocket: primary, secondarySocket: secondary)
        ..setListener(listener);

      final connected = await socket.connect();

      expect(connected, isFalse);
      expect(socket.status, PureSocketStatus.notConnected);
      expect(listener.connectedCount, 0);
    });
  });
}

class _FakeSocket implements IPureSocket {
  final bool connectResult;
  final List<dynamic> sentMessages = [];
  IPureSocketListener? _listener;

  PureSocketStatus _status = PureSocketStatus.notConnected;

  _FakeSocket({required this.connectResult});

  @override
  PureSocketStatus get status => _status;

  @override
  Future<bool> connect() async {
    _status = connectResult ? PureSocketStatus.connected : PureSocketStatus.notConnected;
    if (connectResult) {
      onConnected();
    }
    return connectResult;
  }

  @override
  Future disconnect() async {
    _status = PureSocketStatus.disconnected;
    onClosed();
  }

  @override
  Future stop() => disconnect();

  @override
  void send(dynamic message) {
    sentMessages.add(message);
  }

  void emit(dynamic message) {
    onMessage(message);
  }

  void close([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    _listener?.onClosed(closeCode);
  }

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  void onConnected() {
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    _listener?.onError(err, trace);
  }
}

class _RecordingListener implements IPureSocketListener {
  int connectedCount = 0;
  final List<dynamic> messages = [];
  final List<int?> closedCodes = [];
  final List<Object> errors = [];

  @override
  void onConnected() {
    connectedCount++;
  }

  @override
  void onMessage(dynamic message) {
    messages.add(message);
  }

  @override
  void onClosed([int? closeCode]) {
    closedCodes.add(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    errors.add(err);
  }
}
