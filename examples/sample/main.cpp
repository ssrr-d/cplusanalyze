#include <iostream>

int g_count = 0;
static bool g_enabled = true;

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
    int result = addCount(5);
    std::cout << result << std::endl;
    return 0;
}
