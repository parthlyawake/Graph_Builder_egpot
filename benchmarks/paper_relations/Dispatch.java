class Dispatch {
    void invokeUnknown(Object x) { send(x); }
    void invokeKnown() { send("literal"); }
    void send(String value) { }
    void send(int count) { }
}
