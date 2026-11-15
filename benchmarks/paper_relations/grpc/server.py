import demo_pb2_grpc

class Greeting(demo_pb2_grpc.GreetingServicer):
    def SayHello(self, request, context):
        return request
