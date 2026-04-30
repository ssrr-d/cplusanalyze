#include <iostream>

int g_count = 0;
static bool g_enabled = true;

class Counter {
public:
    Counter() : value_(0) {}

    int add(int delta)
    {
        value_ += delta;
        return addCount(delta);
    }

private:
    int value_;
};

int addCount(int delta)
{
    if (delta < 0) {
        return g_count;
    }
    g_count += delta;
    if (g_count > 100) {
        g_enabled = false;
    }
    return g_count;
}

int main()
{
    Counter counter;
    int result = counter.add(5);
    std::cout << result << std::endl;
    return 0;
}
